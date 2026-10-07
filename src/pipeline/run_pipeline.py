"""
Production-Scale Pipeline Runner
==================================
Executes the RiskPulse processing pipeline in chunked, resumable stages
for the full historical dataset.

This script orchestrates the stage boundaries described in Step 18:
    RAW DATA → VALIDATED DATA → SENTIMENT → MATERIALITY → FINAL RISKSIGNAL

It is designed to be run from Google Colab or any machine with the repository
cloned.  The actual inference logic lives in the src/ modules; this is only a
thin execution coordinator.

Usage
-----
# Dry run (10,000 rows):
python src/pipeline/run_pipeline.py \
    --input data/processed/full_dataset-release.csv \
    --output-dir data/pipeline_output \
    --max-rows 10000 \
    --chunk-size 2000 \
    --batch-size 32

# Full run (no --max-rows):
python src/pipeline/run_pipeline.py \
    --input data/processed/full_dataset-release.csv \
    --output-dir data/pipeline_output \
    --chunk-size 10000 \
    --batch-size 64 \
    --device cuda

# Resume (simply re-run the same command):
python src/pipeline/run_pipeline.py \
    --input data/processed/full_dataset-release.csv \
    --output-dir data/pipeline_output \
    --max-rows 10000

Colab GPU execution procedure
------------------------------
1. Clone repository:   !git clone https://github.com/<org>/Risk-Pulse.git
2. Install deps:       !pip install -r Risk-Pulse/requirements.txt
3. Verify GPU:         import torch; print(torch.cuda.is_available())
4. Verify input:       python src/pipeline/run_pipeline.py --verify-input-only ...
5. Run stage:          python src/pipeline/run_pipeline.py --stages finbert ...
6. Resume if needed:   Re-run the same command; completed chunks are skipped.
7. Validate:           python src/pipeline/run_pipeline.py --validate-output-only ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

# Ensure project root is importable.
_root = Path(__file__).resolve().parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd

from src.pipeline.checkpoint import (
    CheckpointManager,
    build_chunk_id,
    sha256_of_file,
    STATUS_COMPLETE,
)
from src.pipeline.manifest import RunManifest, get_code_version
from src.pipeline.validators import (
    assert_no_leakage,
    validate_finbert_output,
    validate_event_output,
    validate_impact_output,
    validate_row_identity,
    LEAKAGE_COLUMNS,
)

# ---------------------------------------------------------------------------
# Stage names
# ---------------------------------------------------------------------------
STAGE_VALIDATE = "validate"
STAGE_FINBERT = "finbert"
STAGE_EVENT = "event"
STAGE_CLUSTER = "cluster"
STAGE_MATERIALITY = "materiality"
STAGE_IMPACT = "impact"
STAGE_GUARD = "guard"
STAGE_CANONICALIZE = "canonicalize"

ALL_STAGES = [STAGE_VALIDATE, STAGE_FINBERT, STAGE_EVENT, STAGE_CLUSTER, STAGE_MATERIALITY, STAGE_IMPACT, STAGE_GUARD, STAGE_CANONICALIZE]


# ---------------------------------------------------------------------------
# Input validation stage
# ---------------------------------------------------------------------------

def run_validation_stage(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 10_000,
    max_rows: Optional[int] = None,
) -> Path:
    """
    Stage 0: Validate raw input and produce a row-identified CSV.

    Outputs: <output_dir>/validated.parquet
    Each row gets a stable row_id (sequential integer, 0-indexed).
    Future-return columns are stripped from the inference path but the
    full data is preserved for evaluation joins.
    """
    stage_name = STAGE_VALIDATE
    output_path = output_dir / "validated.csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    checkpoint_dir = output_dir / "checkpoints"
    mgr = CheckpointManager(checkpoint_dir / f"{stage_name}_manifest.json")
    input_sha256 = sha256_of_file(input_path)

    manifest = mgr.load_or_create(
        run_id=uuid.uuid4().hex,
        stage_name=stage_name,
        input_path=str(input_path),
        input_sha256=input_sha256,
        input_row_count=0,
        output_dir=str(output_dir),
        code_version=get_code_version(),
        config_version="v1",
        model_identifiers={},
        device="cpu",
        batch_size=1,
        chunk_size=chunk_size,
    )
    completed_ids = set(manifest.completed_chunk_ids())

    first_write = not output_path.exists() or output_path.stat().st_size == 0
    total_rows = 0
    total_written = 0
    skipped = 0
    run_start = time.time()

    reader = pd.read_csv(
        input_path,
        chunksize=chunk_size,
        lineterminator="\n",
        low_memory=False,
        on_bad_lines="skip",
    )

    for ci, chunk in enumerate(reader):
        n = len(chunk)
        if max_rows is not None and total_rows >= max_rows:
            break
        if max_rows is not None and total_rows + n > max_rows:
            chunk = chunk.head(max_rows - total_rows).copy()
            n = len(chunk)

        chunk_id = build_chunk_id(stage_name, ci)

        if chunk_id in completed_ids:
            print(f"[{stage_name}] Skip completed {chunk_id}")
            skipped += 1
            total_rows += n
            continue

        record = mgr.mark_in_progress(manifest, chunk_id, total_rows, total_rows + n)
        t0 = time.time()

        # Assign stable row_id
        if "row_id" not in chunk.columns:
            chunk = chunk.reset_index(drop=True)
            chunk.insert(0, "row_id", range(total_rows, total_rows + len(chunk)))

        # Verify TWEET column exists
        if "TWEET" not in chunk.columns:
            mgr.mark_failed(manifest, record, "Missing TWEET column")
            raise ValueError(f"Chunk {chunk_id}: Missing TWEET column")

        # Validate that leakage columns are present but NOT fed to model
        # (they can be in the raw validation output for eval purposes)
        leakage_present = [c for c in LEAKAGE_COLUMNS if c in chunk.columns]
        if leakage_present:
            print(
                f"[{stage_name}] NOTE: {leakage_present} present in raw data. "
                f"They will NOT be forwarded to inference stages."
            )

        # Build inference-safe slice (without leakage columns)
        inference_cols = [
            c for c in chunk.columns
            if c not in LEAKAGE_COLUMNS
        ]
        inference_chunk = chunk[inference_cols]

        inference_chunk.to_csv(
            output_path, mode="a", header=first_write, index=False
        )
        first_write = False

        dur = time.time() - t0
        mgr.mark_complete(manifest, record, n, str(output_path), dur)
        total_rows += n
        total_written += n
        print(
            f"[{stage_name}] chunk={chunk_id} rows={n:,} "
            f"speed={n/max(dur,0.001):.0f} rows/s total={total_written:,}"
        )

    print(
        f"\n[{stage_name}] Done: {total_written:,} rows written, "
        f"{skipped} chunks skipped, {time.time()-run_start:.1f}s"
    )
    return output_path


# ---------------------------------------------------------------------------
# FinBERT stage (delegates to existing implementation)
# ---------------------------------------------------------------------------

def run_finbert_stage(
    input_path: Path,
    output_dir: Path,
    batch_size: int = 32,
    chunk_size: int = 10_000,
    max_rows: Optional[int] = None,
    device: Optional[str] = None,
) -> Path:
    """
    Stage 1: FinBERT sentiment inference.

    Delegates to the updated finbert_inference.infer_csv() which already
    implements checkpoint/resume.
    """
    from src.nlp.finbert_inference import infer_csv

    output_path = output_dir / "finbert_predictions.csv"
    checkpoint_dir = output_dir / "checkpoints"

    infer_csv(
        input_csv=input_path,
        output_csv=output_path,
        batch_size=batch_size,
        chunk_size=chunk_size,
        max_rows=max_rows,
        device=device,
        checkpoint_dir=checkpoint_dir,
    )
    return output_path


# ---------------------------------------------------------------------------
# Event classifier stage (delegates to existing event_classifier_v2)
# ---------------------------------------------------------------------------

def run_event_stage(
    input_path: Path,
    output_dir: Path,
    batch_size: int = 32,
    chunk_size: int = 1_000,
    max_rows: Optional[int] = None,
    device: Optional[str] = None,
) -> Path:
    """
    Stage 2: Two-stage relevance + event classification.

    Uses event_classifier_v2 which already has chunked execution.
    This wrapper adds checkpoint tracking on top.
    """
    stage_name = "event_classifier"
    output_path = output_dir / "event_predictions.csv"
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    mgr = CheckpointManager(checkpoint_dir / f"{stage_name}_manifest.json")
    input_sha256 = sha256_of_file(input_path)

    import torch
    _device = device

    manifest = mgr.load_or_create(
        run_id=uuid.uuid4().hex,
        stage_name=stage_name,
        input_path=str(input_path),
        input_sha256=input_sha256,
        input_row_count=0,
        output_dir=str(output_dir),
        code_version=get_code_version(),
        config_version="v1",
        model_identifiers={"event_classifier": "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"},
        device=_device or "auto",
        batch_size=batch_size,
        chunk_size=chunk_size,
    )
    completed_ids = set(manifest.completed_chunk_ids())

    from src.nlp.event_classifier_v2 import (
        build_classifier, classify_batch,
        RELEVANCE_DESCRIPTIONS, EVENT_DESCRIPTIONS, EVENT_LABELS,
    )

    first_write = not output_path.exists() or output_path.stat().st_size == 0
    total_rows = 0
    total_written = 0
    skipped = 0
    run_start = time.time()

    # Lazy model load — only load if there's actual work to do
    classifier = None

    reader = pd.read_csv(
        input_path,
        chunksize=chunk_size,
        lineterminator="\n",
        low_memory=False,
        on_bad_lines="skip",
    )

    for ci, chunk in enumerate(reader):
        n = len(chunk)
        if max_rows is not None and total_rows >= max_rows:
            break
        if max_rows is not None and total_rows + n > max_rows:
            chunk = chunk.head(max_rows - total_rows).copy()
            n = len(chunk)

        chunk_id = build_chunk_id(stage_name, ci)

        if chunk_id in completed_ids:
            print(f"[{stage_name}] Skip completed {chunk_id}")
            skipped += 1
            total_rows += n
            continue

        # Load model on first real chunk
        if classifier is None:
            classifier = build_classifier(
                "MoritzLaurer/deberta-v3-base-zeroshot-v2.0",
                _device,
                use_fp16=True,
            )

        # Leakage guard
        assert_no_leakage(chunk, context=f"Event classifier input chunk {chunk_id}")

        record = mgr.mark_in_progress(manifest, chunk_id, total_rows, total_rows + n)
        t0 = time.time()

        text_col = next(
            (c for c in ("TWEET", "text", "TEXT", "tweet") if c in chunk.columns),
            None,
        )
        if text_col is None:
            mgr.mark_failed(manifest, record, "No text column found")
            raise ValueError(f"Chunk {chunk_id}: No text column found")

        texts = (
            chunk[text_col].fillna("").astype(str)
            .str.replace(r"\s+", " ", regex=True).str.strip().tolist()
        )

        relevance_results = classify_batch(
            classifier, texts, RELEVANCE_DESCRIPTIONS, "This text is about {}.", batch_size
        )

        relevance_labels = []
        relevance_scores = []
        event_labels_list = []
        event_scores_list = []
        relevant_indices = []

        for i, result in enumerate(relevance_results):
            top_label = result["labels"][0]
            score = float(result["scores"][0])
            relevance_labels.append(
                "FINANCIAL_EVENT" if top_label == RELEVANCE_DESCRIPTIONS[0] else "NO_MATERIAL_EVENT"
            )
            relevance_scores.append(score)
            if top_label == RELEVANCE_DESCRIPTIONS[0]:
                relevant_indices.append(i)

        event_labels_list = ["NO_EVENT"] * len(texts)
        event_scores_list = [0.0] * len(texts)

        if relevant_indices:
            rel_texts = [texts[i] for i in relevant_indices]
            event_results = classify_batch(
                classifier, rel_texts, EVENT_DESCRIPTIONS, "This text describes {}.", batch_size
            )
            for local_i, res in enumerate(event_results):
                orig_i = relevant_indices[local_i]
                top_desc = res["labels"][0]
                sc = float(res["scores"][0])
                li = EVENT_DESCRIPTIONS.index(top_desc)
                event_labels_list[orig_i] = EVENT_LABELS[li]
                event_scores_list[orig_i] = sc

        out = chunk.copy()
        out["FINANCIAL_RELEVANCE"] = relevance_labels
        out["RELEVANCE_CONFIDENCE"] = relevance_scores
        out["EVENT_TYPE"] = event_labels_list
        out["EVENT_CONFIDENCE"] = event_scores_list

        # Validate event output
        val = validate_event_output(out)
        if not val.valid:
            mgr.mark_failed(manifest, record, str(val.errors))
            raise ValueError(f"Chunk {chunk_id} event validation failed: {val.errors}")

        out.to_csv(output_path, mode="a", header=first_write, index=False)
        first_write = False

        dur = time.time() - t0
        mgr.mark_complete(manifest, record, n, str(output_path), dur)
        total_rows += n
        total_written += n
        print(
            f"[{stage_name}] chunk={chunk_id} rows={n:,} "
            f"speed={n/max(dur,0.001):.0f} rows/s total={total_written:,}"
        )

    print(f"\n[{stage_name}] Done: {total_written:,} rows, {skipped} skipped, {time.time()-run_start:.1f}s")
    return output_path


# ---------------------------------------------------------------------------
# Clustering stage
# ---------------------------------------------------------------------------

def run_cluster_stage(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 10_000,
    max_rows: Optional[int] = None,
) -> Path:
    """
    Stage 3.5: Cluster events and compute novelty.
    """
    stage_name = STAGE_CLUSTER
    output_path = output_dir / "event_clustered.csv"
    
    from src.risk.event_clusterer import EventClusterer
    from src.risk.risk_signal import RiskSignal, Evidence
    
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    mgr = CheckpointManager(checkpoint_dir / f"{stage_name}_manifest.json")
    input_sha256 = sha256_of_file(input_path)
    
    df = pd.read_csv(input_path, on_bad_lines="skip", low_memory=False)
    if max_rows is not None:
        df = df.head(max_rows)
        
    clusterer = EventClusterer()
    novelties = []
    
    for idx, row in df.iterrows():
        text = str(row.get("TWEET", ""))
        ts_str = str(row.get("DATE", ""))
        try:
            ts = pd.to_datetime(ts_str)
            if ts.tzinfo is None:
                from datetime import timezone
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            from datetime import timezone, datetime
            ts = datetime.now(timezone.utc)
            
        source_val = str(row.get("AUTHOR", "news"))
            
        s = RiskSignal(
            entity=str(row.get("STOCK", "")),
            source=source_val,
            sentiment_score=float(row.get("FINBERT_SCORE", 0.0)),
            event_type=str(row.get("EVENT_TYPE", "Other / Unclear")),
            event_confidence=float(row.get("EVENT_CONFIDENCE", 0.0)),
            materiality="UNKNOWN",
            timestamp=ts,
            evidence=Evidence(text=text)
        )
        s._row_id = str(row.get("row_id", idx))
        
        s = clusterer.process_signal(s)
        novelties.append(s.novelty)
        
    df["NOVELTY"] = novelties
    df.to_csv(output_path, index=False)
    print(f"[{stage_name}] Clustered {len(df)} events.")
    
    mgr.load_or_create(
        run_id=uuid.uuid4().hex,
        stage_name=stage_name,
        input_path=str(input_path),
        input_sha256=input_sha256,
        input_row_count=len(df),
        output_dir=str(output_dir),
        code_version=get_code_version(),
        config_version="v1",
        model_identifiers={},
        device="cpu",
        batch_size=1,
        chunk_size=len(df),
    )
    
    return output_path

# ---------------------------------------------------------------------------
# Materiality stage (delegates to event_materiality_v4)
# ---------------------------------------------------------------------------

def run_materiality_stage(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 50_000,
    max_rows: Optional[int] = None,
) -> Path:
    """
    Stage 3: Deterministic event materiality classification.

    Delegates to event_materiality_v4.classify_chunked() which is purely
    CPU-bound regex / rule-based — no model required.
    """
    from src.nlp.event_materiality_v4 import classify_chunked

    output_path = output_dir / "event_materiality.csv"
    checkpoint_dir = output_dir / "checkpoints"

    classify_chunked(
        input_path=input_path,
        output_path=output_path,
        chunk_size=chunk_size,
        max_rows=max_rows,
        checkpoint_dir=checkpoint_dir,
    )
    return output_path


# ---------------------------------------------------------------------------
# Impact scoring stage
# ---------------------------------------------------------------------------

def run_impact_stage(
    input_path: Path,
    finbert_path: Path,
    output_dir: Path,
    chunk_size: int = 50_000,
    max_rows: Optional[int] = None,
) -> Path:
    """
    Stage 4: Deterministic impact scoring via ImpactScorer.

    Merges materiality output with FinBERT predictions on row_id,
    then scores each row. Pure CPU, no model required.
    """
    stage_name = STAGE_IMPACT
    output_path = output_dir / "impact_scored.csv"
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    from src.risk.impact_scorer import ImpactScorer

    scorer = ImpactScorer()
    mgr = CheckpointManager(checkpoint_dir / f"{stage_name}_manifest.json")
    input_sha256 = sha256_of_file(input_path)

    manifest = mgr.load_or_create(
        run_id=uuid.uuid4().hex,
        stage_name=stage_name,
        input_path=str(input_path),
        input_sha256=input_sha256,
        input_row_count=0,
        output_dir=str(output_dir),
        code_version=get_code_version(),
        config_version="v1",
        model_identifiers={"impact_scorer": "v1_deterministic"},
        device="cpu",
        batch_size=1,
        chunk_size=chunk_size,
    )
    completed_ids = set(manifest.completed_chunk_ids())

    # Load FinBERT predictions once (these are compact — safe to load fully)
    print(f"[{stage_name}] Loading FinBERT predictions: {finbert_path}")
    df_fin = pd.read_csv(finbert_path, low_memory=False)

    first_write = not output_path.exists() or output_path.stat().st_size == 0
    total_rows = 0
    total_written = 0
    skipped = 0
    run_start = time.time()

    reader = pd.read_csv(
        input_path,
        chunksize=chunk_size,
        on_bad_lines="skip",
        low_memory=False,
    )

    for ci, chunk in enumerate(reader):
        n = len(chunk)
        if max_rows is not None and total_rows >= max_rows:
            break
        if max_rows is not None and total_rows + n > max_rows:
            chunk = chunk.head(max_rows - total_rows).copy()
            n = len(chunk)

        chunk_id = build_chunk_id(stage_name, ci)

        if chunk_id in completed_ids:
            print(f"[{stage_name}] Skip completed {chunk_id}")
            skipped += 1
            total_rows += n
            continue

        record = mgr.mark_in_progress(manifest, chunk_id, total_rows, total_rows + n)
        t0 = time.time()

        # Merge with FinBERT on row_id
        chunk_fin = chunk.merge(
            df_fin[["row_id", "FINBERT_SCORE", "FINBERT_LABEL"]],
            on="row_id", how="left",
        )

        # Score each row
        impact_scores = []
        impact_reasons = []
        impact_tiers = []

        for _, row in chunk_fin.iterrows():
            event_type = str(row.get("FINAL_EVENT_TYPE", row.get("EVENT_TYPE", "Other / Unclear")))
            materiality = str(row.get("EVENT_MATERIALITY", "NO_EVENT"))
            confidence = float(row.get("EVENT_CONFIDENCE", 0.0))
            sentiment = float(row.get("FINBERT_SCORE", 0.0))
            novelty = float(row.get("NOVELTY", 1.0))

            score, reason, tier = scorer.score_dataframe_row(
                event_type=event_type,
                materiality=materiality,
                event_confidence=confidence,
                sentiment_score=sentiment,
                source_credibility=1.0,
                novelty=novelty,
            )
            impact_scores.append(score)
            impact_reasons.append(reason)
            impact_tiers.append(tier)

        chunk_fin["IMPACT_SCORE"] = impact_scores
        chunk_fin["IMPACT_REASON"] = impact_reasons
        chunk_fin["IMPACT_TIER"] = impact_tiers

        # Validate
        val = validate_impact_output(chunk_fin)
        if not val.valid:
            mgr.mark_failed(manifest, record, str(val.errors))
            raise ValueError(f"Chunk {chunk_id} impact validation failed: {val.errors}")

        chunk_fin.to_csv(output_path, mode="a", header=first_write, index=False)
        first_write = False

        dur = time.time() - t0
        mgr.mark_complete(manifest, record, n, str(output_path), dur)
        total_rows += n
        total_written += n
        print(
            f"[{stage_name}] chunk={chunk_id} rows={n:,} "
            f"speed={n/max(dur,0.001):.0f} rows/s total={total_written:,}"
        )

    print(f"\n[{stage_name}] Done: {total_written:,} rows, {skipped} skipped, {time.time()-run_start:.1f}s")
    return output_path


# ---------------------------------------------------------------------------
# Guard stage
# ---------------------------------------------------------------------------

def run_guard_stage(
    input_path: Path,
    output_dir: Path,
    chunk_size: int = 50_000,
    max_rows: Optional[int] = None,
) -> Path:
    stage_name = STAGE_GUARD
    output_path = output_dir / "guard_scored.csv"
    checkpoint_dir = output_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    from src.nlp.entity_normalizer import EntityNormalizer
    from src.risk.credit_event_guard import check_credit_event_guard

    normalizer = EntityNormalizer()
    mgr = CheckpointManager(checkpoint_dir / f"{stage_name}_manifest.json")
    input_sha256 = sha256_of_file(input_path)

    manifest = mgr.load_or_create(
        run_id=uuid.uuid4().hex,
        stage_name=stage_name,
        input_path=str(input_path),
        input_sha256=input_sha256,
        input_row_count=0,
        output_dir=str(output_dir),
        code_version=get_code_version(),
        config_version="v1",
        model_identifiers={"guard": "v1_deterministic"},
        device="cpu",
        batch_size=1,
        chunk_size=chunk_size,
    )
    completed_ids = set(manifest.completed_chunk_ids())

    first_write = not output_path.exists() or output_path.stat().st_size == 0
    total_rows = 0
    total_written = 0
    skipped = 0
    run_start = time.time()

    reader = pd.read_csv(
        input_path,
        chunksize=chunk_size,
        on_bad_lines="skip",
        low_memory=False,
    )

    for ci, chunk in enumerate(reader):
        n = len(chunk)
        if max_rows is not None and total_rows >= max_rows:
            break
        if max_rows is not None and total_rows + n > max_rows:
            chunk = chunk.head(max_rows - total_rows).copy()
            n = len(chunk)

        chunk_id = build_chunk_id(stage_name, ci)
        if chunk_id in completed_ids:
            print(f"[{stage_name}] Skip completed {chunk_id}")
            skipped += 1
            total_rows += n
            continue

        record = mgr.mark_in_progress(manifest, chunk_id, total_rows, total_rows + n)
        t0 = time.time()

        guard_pass = []
        guard_reason = []
        canonical_entities = []
        entity_statuses = []

        for _, row in chunk.iterrows():
            cand = str(row.get("STOCK", ""))
            text = str(row.get("TWEET", ""))
            event_type = str(row.get("EVENT_TYPE", ""))

            norm_res = normalizer.normalize(cand)
            canonical_entities.append(norm_res["canonical_entity"])
            entity_statuses.append(norm_res["entity_status"])

            if event_type == "Credit Event":
                passed, reason = check_credit_event_guard(
                    text=text,
                    candidate_entity=norm_res["candidate_entity"],
                    canonical_entity=norm_res["canonical_entity"],
                    entity_status=norm_res["entity_status"]
                )
                guard_pass.append(passed)
                guard_reason.append(reason)
            else:
                guard_pass.append(True)
                guard_reason.append("NOT_APPLICABLE")

        chunk["canonical_entity"] = canonical_entities
        chunk["entity_status"] = entity_statuses
        chunk["credit_guard_pass"] = guard_pass
        chunk["credit_guard_reason"] = guard_reason

        chunk.to_csv(output_path, mode="a", header=first_write, index=False)
        first_write = False

        dur = time.time() - t0
        mgr.mark_complete(manifest, record, n, str(output_path), dur)
        total_rows += n
        total_written += n
        print(f"[{stage_name}] chunk={chunk_id} rows={n:,}")

    print(f"\n[{stage_name}] Done: {total_written:,} rows, {skipped} skipped, {time.time()-run_start:.1f}s")
    return output_path


# ---------------------------------------------------------------------------
# Canonicalize stage
# ---------------------------------------------------------------------------

def run_canonicalize_stage(
    input_path: Path,
    output_dir: Path
) -> Path:
    stage_name = STAGE_CANONICALIZE
    output_path = output_dir / "canonical_events.csv"
    
    from src.risk.event_clusterer import EventClusterer
    from src.risk.risk_signal import RiskSignal, Evidence
    from src.risk.canonical_event import CanonicalEvent
    from datetime import datetime, timezone
    import uuid
    import hashlib
    
    print(f"[{stage_name}] Loading guard output from {input_path}")
    df = pd.read_csv(input_path, low_memory=False)
    
    # 1. Input observation count
    total_obs = len(df)
    
    # 2. Number of filtering buckets
    no_event = len(df[df["EVENT_MATERIALITY"] == "NO_EVENT"])
    non_material = len(df[df["EVENT_MATERIALITY"] == "NON_MATERIAL_FINANCIAL_CONTENT"])
    material_obs = len(df[df["EVENT_MATERIALITY"] == "MATERIAL_EVENT"])
    
    def is_valid_material(r):
        if r.get("EVENT_MATERIALITY") != "MATERIAL_EVENT":
            return False
        if r.get("EVENT_TYPE") == "Credit Event" and not r.get("credit_guard_pass"):
            return False
        return True
    
    valid_mask = df.apply(is_valid_material, axis=1)
    material_df = df[valid_mask].copy()
    
    entering_clustering = len(material_df)
    
    # 4. Canonical event materialization
    clusterer = EventClusterer()
    
    for idx, row in material_df.iterrows():
        text = str(row.get("TWEET", ""))
        ts_str = str(row.get("DATE", ""))
        try:
            ts = pd.to_datetime(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)
            
        source_val = str(row.get("AUTHOR", "news"))
            
        s = RiskSignal(
            entity=str(row.get("STOCK", "")),
            source=source_val,
            sentiment_score=float(row.get("FINBERT_SCORE", 0.0)),
            event_type=str(row.get("EVENT_TYPE", "Other / Unclear")),
            event_confidence=float(row.get("EVENT_CONFIDENCE", 0.0)),
            materiality="MATERIAL_EVENT",
            timestamp=ts,
            evidence=Evidence(text=text)
        )
        
        s._row_id = str(row.get("row_id", idx))
        s._tweet_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        s._impact_score = float(row.get("IMPACT_SCORE", 0.0))
        s._impact_tier = str(row.get("IMPACT_TIER", ""))
        s._canonical_entity = str(row.get("canonical_entity", ""))
        s._entity_status = str(row.get("entity_status", ""))
        s._credit_guard_reason = str(row.get("credit_guard_reason", ""))
        
        clusterer.process_signal(s)
        
    canonical_events = []
    
    for cluster in clusterer.clusters:
        cid = cluster.cluster_id
        signals = [cand.signal for cand in cluster.candidates]
        
        obs_count = len(signals)
        max_impact = max((getattr(sig, "_impact_score", 0.0) for sig in signals), default=0.0)
        rep_signal = max(signals, key=lambda x: getattr(x, "_impact_score", 0.0))
        avg_sentiment = sum(sig.sentiment_score for sig in signals) / obs_count
        max_conf = max(sig.event_confidence for sig in signals)
        
        event = CanonicalEvent(
            event_id=uuid.uuid4().hex,
            cluster_id=cid,
            canonical_entity=getattr(rep_signal, "_canonical_entity", rep_signal.entity),
            entity_status=getattr(rep_signal, "_entity_status", "valid"),
            event_type=rep_signal.event_type,
            timestamp=rep_signal.timestamp,
            sentiment_score=avg_sentiment,
            event_confidence=max_conf,
            materiality="MATERIAL_EVENT",
            impact_score=max_impact,
            impact_tier=getattr(rep_signal, "_impact_tier", "LOW"),
            novelty=getattr(rep_signal, "novelty", 1.0),
            observation_count=obs_count,
            source_types=list(set(sig.source for sig in signals)),
            representative_source_credibility=1.0,
            representative_text=rep_signal.evidence.text,
            representative_url=None,
            source_row_ids=[getattr(sig, "_row_id", "") for sig in signals],
            source_tweet_hashes=[getattr(sig, "_tweet_hash", "") for sig in signals],
            credit_guard_reason=getattr(rep_signal, "_credit_guard_reason", "") if rep_signal.event_type == "Credit Event" else None
        )
        canonical_events.append(event)
        
    out_df = pd.DataFrame([e.model_dump() for e in canonical_events])
    out_df.to_csv(output_path, index=False)
    print(f"[{stage_name}] Generated {len(canonical_events)} canonical events.")
    
    return output_path


# ---------------------------------------------------------------------------
# Performance reporter
# ---------------------------------------------------------------------------

def report_performance(output_dir: Path) -> None:
    """Print a performance summary across all completed stages."""
    checkpoint_dir = output_dir / "checkpoints"
    print("\n" + "=" * 60)
    print("PERFORMANCE SUMMARY")
    print("=" * 60)

    for stage in ALL_STAGES:
        manifest_path = checkpoint_dir / f"{stage}_manifest.json"
        if not manifest_path.exists():
            print(f"  {stage}: no manifest found")
            continue
        try:
            with manifest_path.open() as fh:
                data = json.load(fh)
            chunks = data.get("chunks", [])
            done = [c for c in chunks if c.get("status") == STATUS_COMPLETE]
            total_rows = sum(c.get("output_row_count", 0) for c in done)
            total_dur = sum(c.get("duration_seconds", 0) for c in done)
            rps = total_rows / max(total_dur, 0.001)
            print(
                f"  {stage}: chunks={len(done)} rows={total_rows:,} "
                f"duration={total_dur:.1f}s speed={rps:.0f} rows/s"
            )
        except Exception as exc:
            print(f"  {stage}: error reading manifest: {exc}")

    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="RiskPulse production-scale pipeline runner"
    )
    p.add_argument("--input", required=True, help="Raw dataset CSV path")
    p.add_argument("--output-dir", required=True, help="Output directory for all stage outputs")
    p.add_argument(
        "--stages",
        nargs="+",
        choices=ALL_STAGES,
        default=ALL_STAGES,
        help="Stages to execute (default: all)",
    )
    p.add_argument("--chunk-size", type=int, default=10_000, help="Rows per chunk")
    p.add_argument("--batch-size", type=int, default=256, help="Model inference batch size")
    p.add_argument("--max-rows", type=int, default=None, help="Limit rows (dry run)")
    p.add_argument("--device", default=None, help="Device: cpu / cuda / cuda:0")
    p.add_argument("--verify-input-only", action="store_true")
    p.add_argument("--validate-output-only", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    print(f"\nInput: {input_path}")
    print(f"Output: {output_dir}")
    print(f"Input SHA-256 (first 10MB+size): {sha256_of_file(input_path)}")
    print(f"Stages: {args.stages}")
    print(f"chunk_size={args.chunk_size}  batch_size={args.batch_size}  max_rows={args.max_rows}")

    if args.verify_input_only:
        print("Input verified. Exiting (--verify-input-only).")
        return

    if args.validate_output_only:
        report_performance(output_dir)
        return

    validated_path: Optional[Path] = None
    finbert_path: Optional[Path] = None
    event_path: Optional[Path] = None
    materiality_path: Optional[Path] = None
    impact_path: Optional[Path] = None

    run_start = time.time()

    if STAGE_VALIDATE in args.stages:
        print("\n--- STAGE: validate ---")
        validated_path = run_validation_stage(
            input_path, output_dir,
            chunk_size=args.chunk_size,
            max_rows=args.max_rows,
        )
    else:
        validated_path = output_dir / "validated.csv"

    if STAGE_FINBERT in args.stages:
        if validated_path is None or not validated_path.exists():
            print("WARNING: validated.csv not found; using raw input for FinBERT")
            validated_path = input_path
        print("\n--- STAGE: finbert ---")
        finbert_path = run_finbert_stage(
            validated_path, output_dir,
            batch_size=args.batch_size,
            chunk_size=args.chunk_size,
            max_rows=args.max_rows,
            device=args.device,
        )
    else:
        finbert_path = output_dir / "finbert_predictions.csv"

    if STAGE_EVENT in args.stages:
        if validated_path is None or not validated_path.exists():
            print("WARNING: validated.csv not found; using raw input for Event Classifier")
            validated_path = input_path
        print("\n--- STAGE: event ---")
        event_path = run_event_stage(
            validated_path, output_dir,
            batch_size=args.batch_size,
            chunk_size=args.chunk_size,
            max_rows=args.max_rows,
            device=args.device,
        )
    else:
        event_path = output_dir / "event_predictions.csv"

    if STAGE_CLUSTER in args.stages:
        event_path = output_dir / "event_predictions.csv"
        if not event_path.exists():
            print("WARNING: event_predictions.csv not found; skipping cluster.")
        else:
            print("\n--- STAGE: cluster ---")
            clustered_path = run_cluster_stage(
                event_path, output_dir,
                chunk_size=args.chunk_size,
                max_rows=args.max_rows,
            )
    else:
        clustered_path = output_dir / "event_clustered.csv"

    if STAGE_MATERIALITY in args.stages:
        cluster_in = clustered_path or output_dir / "event_clustered.csv"
        if not cluster_in.exists():
            print(
                "WARNING: event_clustered.csv not found; "
                "materiality stage requires clustered output. Skipping."
            )
        else:
            print("\n--- STAGE: materiality ---")
            materiality_path = run_materiality_stage(
                cluster_in, output_dir,
                chunk_size=args.chunk_size * 5,  # materiality is CPU-only, larger chunks OK
                max_rows=args.max_rows,
            )
    else:
        materiality_path = output_dir / "event_materiality.csv"

    if STAGE_IMPACT in args.stages:
        mat_in = materiality_path or output_dir / "event_materiality.csv"
        fin_in = finbert_path or output_dir / "finbert_predictions.csv"
        if not mat_in.exists() or not fin_in.exists():
            print("WARNING: Missing materiality or finbert outputs; skipping impact stage.")
        else:
            print("\n--- STAGE: impact ---")
            impact_path = run_impact_stage(
                mat_in, fin_in, output_dir,
                chunk_size=args.chunk_size * 5,
                max_rows=args.max_rows,
            )
    else:
        impact_path = output_dir / "impact_scored.csv"

    if STAGE_GUARD in args.stages:
        imp_in = impact_path or output_dir / "impact_scored.csv"
        if not imp_in.exists():
            print("WARNING: Missing impact output; skipping guard stage.")
        else:
            print("\n--- STAGE: guard ---")
            guard_path = run_guard_stage(
                imp_in, output_dir,
                chunk_size=args.chunk_size * 5,
                max_rows=args.max_rows,
            )
    else:
        guard_path = output_dir / "guard_scored.csv"

    if STAGE_CANONICALIZE in args.stages:
        guard_in = guard_path or output_dir / "guard_scored.csv"
        if not guard_in.exists():
            print("WARNING: Missing guard output; skipping canonicalize stage.")
        else:
            print("\n--- STAGE: canonicalize ---")
            canonical_path = run_canonicalize_stage(
                guard_in, output_dir
            )

    total_time = time.time() - run_start
    print(f"\nTotal pipeline time: {total_time:.1f}s")
    report_performance(output_dir)


if __name__ == "__main__":
    main()
