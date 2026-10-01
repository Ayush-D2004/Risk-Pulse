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
-----------------------------
This script performs inference only. It does NOT use:
    LSTM_POLARITY
    TEXTBLOB_POLARITY
    1_DAY_RETURN ... 7_DAY_RETURN
    VOLATILITY_10D / VOLATILITY_30D
as model inputs.

Future returns remain evaluation-only variables.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


MODEL_NAME = "ProsusAI/finbert"


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
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
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
) -> None:
    """
    Run resumable-ish chunked inference.

    Existing output is preserved when overwrite=False. If interrupted, rerun
    with the same output path; completed chunks are skipped based on the
    output row count. For strongest reproducibility, use a fresh output path
    for a changed model/configuration.
    """
    input_csv = Path(input_csv)
    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    if output_csv.exists() and overwrite:
        output_csv.unlink()

    model = FinBERT(
        model_name=MODEL_NAME,
        device=device,
        max_length=max_length,
    )

    completed = 0
    if output_csv.exists():
        try:
            completed = sum(1 for _ in output_csv.open("r", encoding="utf-8")) - 1
            completed = max(completed, 0)
            print(f"[resume] existing predictions: {completed:,}")
        except OSError:
            completed = 0

    first_write = not output_csv.exists()

    reader = pd.read_csv(
        input_csv,
        chunksize=chunk_size,
        low_memory=False,
    )

    processed = 0
    skipped = 0

    for chunk_index, chunk in enumerate(reader):
        if max_rows is not None and processed >= max_rows:
            break

        if "TWEET" not in chunk.columns:
            raise ValueError("Input CSV must contain a TWEET column.")

        # Respect max_rows without modifying the source file.
        if max_rows is not None:
            remaining = max_rows - processed
            chunk = chunk.iloc[:remaining]

        n = len(chunk)

        # Resume by logical row count.
        if skipped + n <= completed:
            skipped += n
            continue

        if skipped < completed:
            # A previous run ended inside this chunk.
            offset = completed - skipped
            chunk = chunk.iloc[offset:].copy()
            skipped = completed
        else:
            skipped += n

        texts = [normalize_text(x) for x in chunk["TWEET"].tolist()]
        predictions = model.predict(texts, batch_size=batch_size)

        result = pd.DataFrame(
            {
                "row_id": np.arange(
                    completed,
                    completed + len(chunk),
                    dtype=np.int64,
                ),
                "tweet_hash": [tweet_hash(t) for t in texts],
            }
        )

        result = pd.concat(
            [result.reset_index(drop=True), predictions.reset_index(drop=True)],
            axis=1,
        )

        result.to_csv(
            output_csv,
            mode="a",
            header=first_write,
            index=False,
        )
        first_write = False

        completed += len(chunk)
        processed += len(chunk)

        print(
            f"[progress] predictions={completed:,} "
            f"last_chunk={len(chunk):,}"
        )

    print(f"[done] wrote {completed:,} predictions to {output_csv}")


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
    )
