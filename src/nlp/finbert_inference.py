"""
FinBERT batch inference for the RiskPulse historical-text pipeline.

Purpose
-------
Run ProsusAI/FinBERT over a large normalized CSV without loading the entire
dataset or all model outputs into memory.

Input requirements
------------------
A CSV containing at least:
    TWEET
Optionally:
    STOCK, DATE, and any other source columns.

Output
------
A compact CSV containing:
    row_id
    tweet_hash
    FINBERT_POSITIVE
    FINBERT_NEGATIVE
    FINBERT_NEUTRAL
    FINBERT_SCORE
    FINBERT_LABEL

The original dataset should remain untouched. Join this output back to the
source dataset using tweet_hash (or row_id when the same normalized file is
used).

Important methodological rule
------------------------------
This script performs inference only. It does NOT use:
    LSTM_POLARITY
    TEXTBLOB_POLARITY
    1_DAY_RETURN ... 7_DAY_RETURN
    VOLATILITY_10D / VOLATILITY_30D
as model inputs.

Future returns remain evaluation-only variables.

Step 18 additions
-----------------
* Explicit chunk-level checkpointing via src.pipeline.checkpoint.
* Leakage guard: hard check before inference that no forbidden columns exist
  in the model input path.
* Output validation for each chunk before marking it COMPLETE.
* Configurable device, batch_size, chunk_size via CLI.
* Run manifest creation and persistence.
"""

from __future__ import annotations

import argparse
import hashlib
import time
import uuid
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src.pipeline.checkpoint import (
    CheckpointManager,
    build_chunk_id,
    sha256_of_file,
)
from src.pipeline.manifest import RunManifest, get_code_version
from src.pipeline.validators import (
    assert_no_leakage,
    validate_finbert_output,
    validate_row_identity,
)
from src.pipeline.device_utils import resolve_device, verify_device_execution



MODEL_NAME = "ProsusAI/finbert"

# Columns that must NEVER enter the model input path.
_INFERENCE_FORBIDDEN_COLUMNS = frozenset([
    "1_DAY_RETURN", "2_DAY_RETURN", "3_DAY_RETURN", "7_DAY_RETURN",
    "LSTM_POLARITY", "TEXTBLOB_POLARITY",
])


def normalize_text(value: object) -> str:
    """Normalize only enough to make hashing and inference deterministic."""
    if pd.isna(value):
        return ""
    return " ".join(str(value).replace("\x00", " ").split())


def tweet_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FinBERT:
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        device: str | None = None,
        max_length: int = 256,
    ):
        self.device = resolve_device(device)
        self.max_length = max_length

        print(f"[FinBERT] model={model_name}")
        print(f"[FinBERT] device={self.device}")

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

        self.id2label = {
            int(k): str(v).lower()
            for k, v in self.model.config.id2label.items()
        }

        # Fail early if a different/incompatible model is accidentally supplied.
        required = {"positive", "negative", "neutral"}
        if not required.issubset(set(self.id2label.values())):
            raise RuntimeError(
                f"Expected FinBERT labels {required}; got {self.id2label}"
            )

    @torch.inference_mode()
    def predict(self, texts: list[str], batch_size: int = 32) -> pd.DataFrame:
        records = []

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]

            encoded = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            )
            encoded = {k: v.to(self.device) for k, v in encoded.items()}

            verify_device_execution(self.model, encoded, self.device)

            logits = self.model(**encoded).logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()

            for p in probs:
                values = {
                    self.id2label[i]: float(prob)
                    for i, prob in enumerate(p)
                }

                positive = values["positive"]
                negative = values["negative"]
                neutral = values["neutral"]

                # Required Risk Engine representation:
                # [-1, +1], where positive and negative probabilities compete.
                score = positive - negative

                label = max(
                    ("positive", "negative", "neutral"),
                    key=lambda x: values[x],
                )

                records.append(
                    {
                        "FINBERT_POSITIVE": positive,
                        "FINBERT_NEGATIVE": negative,
                        "FINBERT_NEUTRAL": neutral,
                        "FINBERT_SCORE": score,
                        "FINBERT_LABEL": label,
                    }
                )

        return pd.DataFrame.from_records(records)


def infer_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    batch_size: int = 32,
    chunk_size: int = 10_000,
    max_rows: int | None = None,
    device: str | None = None,
    max_length: int = 256,
    overwrite: bool = False,
    checkpoint_dir: str | Path | None = None,
) -> None:
    """
    Run chunked, checkpointed FinBERT inference.

    Checkpointing
    -------------
    Each chunk is tracked in a JSON manifest. If the process is interrupted,
    rerunning with the same output path resumes from the next incomplete chunk
    without recomputing already-validated chunks.

    Leakage protection
    ------------------
    Before inference, a hard guard verifies that no future-return or
    reference-sentiment columns are present in the model input slice.
    """
    input_csv = Path(input_csv)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    if output_csv.exists() and overwrite:
        output_csv.unlink()
        print(f"[FinBERT] Removed existing output: {output_csv}")

    # ------------------------------------------------------------------
    # Resolve checkpoint path
    # ------------------------------------------------------------------
    if checkpoint_dir is None:
        checkpoint_dir = output_csv.parent / "checkpoints"
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    stage_name = "finbert"
    manifest_path = checkpoint_dir / f"{stage_name}_manifest.json"

    # ------------------------------------------------------------------
    # Build run manifest
    # ------------------------------------------------------------------
    resolved_device = resolve_device(device)
    run_manifest = RunManifest(
        stage_name=stage_name,
        input_path=input_csv,
        output_dir=output_csv.parent,
        chunk_size=chunk_size,
        batch_size=batch_size,
        device=resolved_device,
        model_identifiers={"finbert": MODEL_NAME},
        config_version="v1",
    )

    # ------------------------------------------------------------------
    # Load / create checkpoint manifest
    # ------------------------------------------------------------------
    mgr = CheckpointManager(manifest_path)
    input_sha256 = sha256_of_file(input_csv)

    model = FinBERT(
        model_name=MODEL_NAME,
        device=resolved_device,
        max_length=max_length,
    )

    # ------------------------------------------------------------------
    # Determine total rows and build chunk plan
    # ------------------------------------------------------------------
    # We stream the full CSV to avoid full load into RAM.
    # Build an index of chunk boundaries once upfront.
    print(f"[FinBERT] Scanning input to build chunk plan: {input_csv}")
    total_rows = 0
    chunk_plan = []   # list of (chunk_index, start, end)

    reader = pd.read_csv(
        input_csv,
        chunksize=chunk_size,
        lineterminator="\n",
        low_memory=False,
    )
    for ci, chunk in enumerate(reader):
        n = len(chunk)
        if max_rows is not None and total_rows >= max_rows:
            break
        if max_rows is not None:
            n = min(n, max_rows - total_rows)
        chunk_plan.append((ci, total_rows, total_rows + n))
        total_rows += n
        if max_rows is not None and total_rows >= max_rows:
            break

    print(f"[FinBERT] Chunk plan: {len(chunk_plan)} chunks, {total_rows:,} rows")
    run_manifest.input_row_count = total_rows

    # ------------------------------------------------------------------
    # Load checkpoint
    # ------------------------------------------------------------------
    checkpoint = mgr.load_or_create(
        run_id=run_manifest.run_id,
        stage_name=stage_name,
        input_path=str(input_csv),
        input_sha256=input_sha256,
        input_row_count=total_rows,
        output_dir=str(output_csv.parent),
        code_version=get_code_version(),
        config_version="v1",
        model_identifiers={"finbert": MODEL_NAME},
        device=run_manifest.device,
        batch_size=batch_size,
        chunk_size=chunk_size,
    )
    completed_ids = set(checkpoint.completed_chunk_ids())

    # ------------------------------------------------------------------
    # Determine whether output file already has a header
    # ------------------------------------------------------------------
    first_write = not output_csv.exists() or output_csv.stat().st_size == 0

    # ------------------------------------------------------------------
    # Process chunks
    # ------------------------------------------------------------------
    run_start = time.time()
    reader = pd.read_csv(
        input_csv,
        chunksize=chunk_size,
        lineterminator="\n",
        low_memory=False,
    )

    total_written = 0
    chunks_processed = 0
    chunks_skipped = 0

    for ci, chunk in enumerate(reader):
        if ci >= len(chunk_plan):
            break

        _, start_row, end_row = chunk_plan[ci]

        # Trim chunk to max_rows if needed
        if max_rows is not None and start_row + len(chunk) > max_rows:
            chunk = chunk.iloc[:max_rows - start_row].copy()

        chunk_id = build_chunk_id(stage_name, ci)

        # Skip already-completed chunks
        if chunk_id in completed_ids:
            print(f"[FinBERT] Skipping completed chunk {chunk_id} ({len(chunk):,} rows)")
            chunks_skipped += 1
            continue

        if "TWEET" not in chunk.columns:
            raise ValueError(f"Input CSV must contain a TWEET column (chunk {ci}).")

        # ----------------------------------------------------------------
        # LEAKAGE GUARD — hard check before extracting inference inputs
        # ----------------------------------------------------------------
        assert_no_leakage(chunk, context=f"FinBERT input chunk {chunk_id}")

        chunk_start_time = time.time()
        record = mgr.mark_in_progress(checkpoint, chunk_id, start_row, end_row)

        try:
            texts = [normalize_text(x) for x in chunk["TWEET"].tolist()]

            predictions = model.predict(texts, batch_size=batch_size)

            result = pd.DataFrame(
                {
                    "row_id": np.arange(start_row, start_row + len(chunk), dtype=np.int64),
                    "tweet_hash": [tweet_hash(t) for t in texts],
                }
            )
            result = pd.concat(
                [result.reset_index(drop=True), predictions.reset_index(drop=True)],
                axis=1,
            )

            # ----------------------------------------------------------------
            # Validate chunk output before writing
            # ----------------------------------------------------------------
            val = validate_finbert_output(result)
            if not val.valid:
                raise ValueError(
                    f"Chunk {chunk_id} validation failed:\n{val.report()}"
                )
            if val.invalid_rows > 0:
                print(f"[WARN] chunk {chunk_id}: {val.invalid_rows} invalid rows (reported, not written)")

            result.to_csv(
                output_csv,
                mode="a",
                header=first_write,
                index=False,
            )
            first_write = False

            duration = time.time() - chunk_start_time
            mgr.mark_complete(
                checkpoint,
                record,
                output_row_count=len(result),
                output_path=str(output_csv),
                duration_seconds=duration,
            )

            total_written += len(result)
            chunks_processed += 1
            rows_per_sec = len(result) / max(duration, 0.001)
            print(
                f"[FinBERT] chunk={chunk_id} rows={len(result):,} "
                f"speed={rows_per_sec:.0f} rows/s "
                f"total_written={total_written:,}"
            )

        except Exception as exc:
            mgr.mark_failed(checkpoint, record, str(exc))
            print(f"[ERROR] Chunk {chunk_id} failed: {exc}")
            raise

    # ------------------------------------------------------------------
    # Finalize manifest
    # ------------------------------------------------------------------
    run_duration = time.time() - run_start
    run_manifest.finalize(
        input_row_count=total_rows,
        output_row_count=total_written,
        duration_seconds=run_duration,
    )
    manifest_out = checkpoint_dir / f"{stage_name}_run_manifest.json"
    run_manifest.save(manifest_out)

    print(f"\n[FinBERT] Done.")
    print(f"  chunks_processed={chunks_processed}  chunks_skipped={chunks_skipped}")
    print(f"  total_written={total_written:,}  duration={run_duration:.1f}s")
    print(f"  manifest={manifest_out}")
    print(checkpoint.summary())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run chunked FinBERT inference over a normalized tweet CSV."
    )
    parser.add_argument("--input", required=True, help="Input CSV containing TWEET.")
    parser.add_argument("--output", required=True, help="Prediction CSV path.")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--chunk-size", type=int, default=10_000)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument(
        "--device",
        default=None,
        help="cpu, cuda, cuda:0, etc. Defaults to CUDA when available.",
    )
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--checkpoint-dir",
        default=None,
        help="Directory for checkpoint manifests. Defaults to <output_dir>/checkpoints/",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    infer_csv(
        input_csv=args.input,
        output_csv=args.output,
        batch_size=args.batch_size,
        chunk_size=args.chunk_size,
        max_rows=args.max_rows,
        device=args.device,
        max_length=args.max_length,
        overwrite=args.overwrite,
        checkpoint_dir=args.checkpoint_dir,
    )


# Test run : python src/nlp/finbert_inference.py \
#   --input data/processed/reduced_dataset-release.csv \
#   --output data/processed/finbert_reduced_predictions.csv \
#   --max-rows 5000 \
#   --batch-size 64
