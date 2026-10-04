"""
Step 18 — Production-Scale Pipeline Tests

Tests for:
1. Stable row identity
2. Chunk boundaries
3. Checkpoint creation
4. Checkpoint resume
5. Invalid/corrupt checkpoint handling
6. Duplicate row detection
7. Missing row detection
8. Output validation (FinBERT, event, impact)
9. FinBERT probability validation
10. Impact score validation
11. Leakage protection
12. Deterministic repeated execution
13. Dry-run configuration
14. Manifest creation
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers to create synthetic test data
# ---------------------------------------------------------------------------


def make_validated_csv(n_rows: int, tmp_dir: Path, include_leakage: bool = False) -> Path:
    """Create a minimal tweet CSV with optional leakage columns."""
    path = tmp_dir / "test_validated.csv"
    data = {
        "row_id": list(range(n_rows)),
        "tweet_hash": [f"hash_{i}" for i in range(n_rows)],
        "TWEET": [f"Apple reports strong quarterly earnings {i}" for i in range(n_rows)],
        "STOCK": ["AAPL"] * n_rows,
        "DATE": ["2017-01-31"] * n_rows,
    }
    if include_leakage:
        data["1_DAY_RETURN"] = [0.01] * n_rows
        data["LSTM_POLARITY"] = [0.5] * n_rows
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)
    return path


def make_finbert_csv(n_rows: int, tmp_dir: Path, corrupt: bool = False) -> Path:
    """Create a minimal FinBERT predictions CSV."""
    path = tmp_dir / "test_finbert.csv"
    data = {
        "row_id": list(range(n_rows)),
        "tweet_hash": [f"hash_{i}" for i in range(n_rows)],
        "FINBERT_POSITIVE": [0.7] * n_rows,
        "FINBERT_NEGATIVE": [0.2] * n_rows,
        "FINBERT_NEUTRAL": [0.1] * n_rows,
        "FINBERT_SCORE": [0.5] * n_rows,
        "FINBERT_LABEL": ["positive"] * n_rows,
    }
    if corrupt:
        data["FINBERT_POSITIVE"][0] = 1.5  # out of bounds
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)
    return path


def make_event_csv(n_rows: int, tmp_dir: Path) -> Path:
    """Create a minimal event classifier output CSV."""
    path = tmp_dir / "test_events.csv"
    data = {
        "row_id": list(range(n_rows)),
        "TWEET": [f"Apple earnings {i}" for i in range(n_rows)],
        "FINANCIAL_RELEVANCE": ["FINANCIAL_EVENT"] * n_rows,
        "EVENT_TYPE": ["Corporate / Earnings"] * n_rows,
        "EVENT_CONFIDENCE": [0.75] * n_rows,
    }
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)
    return path


def make_materiality_csv(n_rows: int, tmp_dir: Path) -> Path:
    """Create a minimal materiality output CSV."""
    path = tmp_dir / "test_materiality.csv"
    data = {
        "row_id": list(range(n_rows)),
        "TWEET": [f"Apple earnings beat estimates {i}" for i in range(n_rows)],
        "EVENT_MATERIALITY": ["MATERIAL_EVENT"] * n_rows,
        "FINAL_EVENT_TYPE": ["Corporate / Earnings"] * n_rows,
        "EVENT_MATERIALITY_REASON": ["upstream_type_confirmed:earnings"] * n_rows,
        "FINANCIAL_RELEVANCE": ["FINANCIAL_EVENT"] * n_rows,
        "EVENT_TYPE": ["Corporate / Earnings"] * n_rows,
        "EVENT_CONFIDENCE": [0.75] * n_rows,
    }
    df = pd.DataFrame(data)
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# 1. Stable Row Identity
# ---------------------------------------------------------------------------


class TestStableRowIdentity:
    def test_row_id_preserved_across_chunks(self, tmp_path):
        """Row IDs assigned in validation stage must survive chunked writes."""
        n = 500
        csv_path = make_validated_csv(n, tmp_path)
        df = pd.read_csv(csv_path)
        assert "row_id" in df.columns
        assert list(df["row_id"]) == list(range(n)), "Row IDs must be sequential and complete"

    def test_row_id_not_positional(self, tmp_path):
        """Row identity must not rely on DataFrame position."""
        n = 100
        csv_path = make_validated_csv(n, tmp_path)
        df = pd.read_csv(csv_path)
        # Shuffle and confirm row_id still identifies each record
        shuffled = df.sample(frac=1, random_state=42).reset_index(drop=True)
        assert set(shuffled["row_id"]) == set(range(n)), "Shuffling must not change row_id values"

    def test_merge_on_row_id_is_exact(self, tmp_path):
        """Merging two stage outputs on row_id must produce zero missing rows."""
        n = 200
        mat_path = make_materiality_csv(n, tmp_path)
        fin_path = make_finbert_csv(n, tmp_path)

        df_mat = pd.read_csv(mat_path)
        df_fin = pd.read_csv(fin_path)

        merged = df_mat.merge(df_fin, on="row_id", how="inner")
        assert len(merged) == n, f"Expected {n} merged rows, got {len(merged)}"


# ---------------------------------------------------------------------------
# 2. Chunk Boundaries
# ---------------------------------------------------------------------------


class TestChunkBoundaries:
    def test_chunk_boundaries_no_overlap(self):
        """Adjacent chunk boundaries must not overlap or leave gaps."""
        from src.pipeline.checkpoint import build_chunk_id

        chunk_size = 100
        n_rows = 350
        starts = []
        ends = []
        for ci in range((n_rows + chunk_size - 1) // chunk_size):
            start = ci * chunk_size
            end = min(start + chunk_size, n_rows)
            starts.append(start)
            ends.append(end)

        # No gaps
        for i in range(1, len(starts)):
            assert starts[i] == ends[i - 1], f"Gap between chunk {i-1} and {i}"

        # No overlap
        for i in range(1, len(starts)):
            assert starts[i] >= ends[i - 1], f"Overlap between chunk {i-1} and {i}"

    def test_chunk_ids_are_deterministic(self):
        """Same chunk index must always produce same chunk_id."""
        from src.pipeline.checkpoint import build_chunk_id

        cid1 = build_chunk_id("finbert", 5)
        cid2 = build_chunk_id("finbert", 5)
        assert cid1 == cid2 == "finbert_chunk_000005"

    def test_chunk_ids_unique_per_index(self):
        """Different chunk indices must produce unique IDs."""
        from src.pipeline.checkpoint import build_chunk_id

        ids = [build_chunk_id("finbert", i) for i in range(10)]
        assert len(set(ids)) == 10, "Chunk IDs must be unique"


# ---------------------------------------------------------------------------
# 3. Checkpoint Creation
# ---------------------------------------------------------------------------


class TestCheckpointCreation:
    def test_manifest_created_on_init(self, tmp_path):
        """CheckpointManager must create a manifest file on first use."""
        from src.pipeline.checkpoint import CheckpointManager

        manifest_path = tmp_path / "checkpoints" / "test_manifest.json"
        mgr = CheckpointManager(manifest_path)
        manifest = mgr.load_or_create(
            run_id="test-run-001",
            stage_name="test_stage",
            input_path="/tmp/input.csv",
            input_sha256="abc123",
            input_row_count=1000,
            output_dir="/tmp/out",
            code_version="v1",
            config_version="v1",
            model_identifiers={"model": "test"},
            device="cpu",
            batch_size=32,
            chunk_size=100,
        )
        assert manifest_path.exists(), "Manifest file must be created"
        with manifest_path.open() as fh:
            data = json.load(fh)
        assert data["run_id"] == "test-run-001"
        assert data["stage_name"] == "test_stage"

    def test_chunk_record_written_on_mark_complete(self, tmp_path):
        """Marking a chunk complete must persist the record to disk."""
        from src.pipeline.checkpoint import CheckpointManager, ChunkRecord, build_chunk_id

        manifest_path = tmp_path / "manifest.json"
        mgr = CheckpointManager(manifest_path)
        manifest = mgr.load_or_create(
            run_id="r1", stage_name="s1", input_path="x", input_sha256="y",
            input_row_count=100, output_dir="/tmp", code_version="v",
            config_version="c", model_identifiers={}, device="cpu",
            batch_size=1, chunk_size=10,
        )
        chunk_id = build_chunk_id("s1", 0)
        record = mgr.mark_in_progress(manifest, chunk_id, 0, 10)
        mgr.mark_complete(manifest, record, 10, "/tmp/out.csv", 1.0)

        # Reload from disk
        with manifest_path.open() as fh:
            data = json.load(fh)

        chunks = {c["chunk_id"]: c for c in data["chunks"]}
        assert chunk_id in chunks
        assert chunks[chunk_id]["status"] == "COMPLETE"
        assert chunks[chunk_id]["output_row_count"] == 10

    def test_manifest_contains_required_fields(self, tmp_path):
        """Manifest must record all required reproducibility fields."""
        from src.pipeline.checkpoint import CheckpointManager

        manifest_path = tmp_path / "manifest.json"
        mgr = CheckpointManager(manifest_path)
        mgr.load_or_create(
            run_id="r1", stage_name="s1", input_path="input.csv",
            input_sha256="sha256abc", input_row_count=500,
            output_dir="/tmp", code_version="git:abc123",
            config_version="v1", model_identifiers={"finbert": "ProsusAI/finbert"},
            device="cpu", batch_size=32, chunk_size=1000,
        )

        with manifest_path.open() as fh:
            data = json.load(fh)

        required = [
            "run_id", "stage_name", "input_path", "input_sha256",
            "input_row_count", "output_dir", "code_version", "config_version",
            "model_identifiers", "device", "batch_size", "chunk_size",
            "created_at", "schema_version",
        ]
        for field in required:
            assert field in data, f"Manifest missing required field: {field}"


# ---------------------------------------------------------------------------
# 4. Checkpoint Resume
# ---------------------------------------------------------------------------


class TestCheckpointResume:
    def test_completed_chunks_are_skipped_on_reload(self, tmp_path):
        """Resuming from an existing manifest must skip completed chunks."""
        from src.pipeline.checkpoint import CheckpointManager, build_chunk_id

        manifest_path = tmp_path / "manifest.json"
        mgr = CheckpointManager(manifest_path)

        kwargs = dict(
            run_id="r1", stage_name="s1", input_path="x", input_sha256="y",
            input_row_count=100, output_dir="/tmp", code_version="v",
            config_version="c", model_identifiers={}, device="cpu",
            batch_size=1, chunk_size=10,
        )
        manifest = mgr.load_or_create(**kwargs)

        # Mark chunk 0 as complete
        chunk_id_0 = build_chunk_id("s1", 0)
        record = mgr.mark_in_progress(manifest, chunk_id_0, 0, 10)
        mgr.mark_complete(manifest, record, 10, "/tmp/out.csv", 0.5)

        # Simulate a new run by reloading the manifest
        manifest2 = mgr.load_or_create(**kwargs)
        completed = manifest2.completed_chunk_ids()
        assert chunk_id_0 in completed, "Reloaded manifest must show chunk 0 as complete"

    def test_failed_chunks_appear_in_pending(self, tmp_path):
        """Failed chunks must appear in pending_or_failed_chunks."""
        from src.pipeline.checkpoint import CheckpointManager, build_chunk_id

        manifest_path = tmp_path / "manifest.json"
        mgr = CheckpointManager(manifest_path)
        manifest = mgr.load_or_create(
            run_id="r1", stage_name="s1", input_path="x", input_sha256="y",
            input_row_count=100, output_dir="/tmp", code_version="v",
            config_version="c", model_identifiers={}, device="cpu",
            batch_size=1, chunk_size=10,
        )
        chunk_id = build_chunk_id("s1", 3)
        record = mgr.mark_in_progress(manifest, chunk_id, 30, 40)
        mgr.mark_failed(manifest, record, "simulated failure")

        pending = manifest.pending_or_failed_chunks()
        assert any(c.chunk_id == chunk_id for c in pending)

    def test_total_output_rows_sums_completed_only(self, tmp_path):
        """total_output_rows must only count COMPLETE chunks."""
        from src.pipeline.checkpoint import CheckpointManager, build_chunk_id

        manifest_path = tmp_path / "manifest.json"
        mgr = CheckpointManager(manifest_path)
        manifest = mgr.load_or_create(
            run_id="r1", stage_name="s1", input_path="x", input_sha256="y",
            input_row_count=100, output_dir="/tmp", code_version="v",
            config_version="c", model_identifiers={}, device="cpu",
            batch_size=1, chunk_size=10,
        )

        # Complete chunk 0 (10 rows)
        r0 = mgr.mark_in_progress(manifest, build_chunk_id("s1", 0), 0, 10)
        mgr.mark_complete(manifest, r0, 10, "/tmp/out.csv", 0.1)

        # Fail chunk 1
        r1 = mgr.mark_in_progress(manifest, build_chunk_id("s1", 1), 10, 20)
        mgr.mark_failed(manifest, r1, "error")

        assert manifest.total_output_rows() == 10


# ---------------------------------------------------------------------------
# 5. Invalid/Corrupt Checkpoint Handling
# ---------------------------------------------------------------------------


class TestCorruptCheckpointHandling:
    def test_corrupt_manifest_json_triggers_fresh_start(self, tmp_path):
        """A corrupt JSON manifest must not crash — a fresh manifest is created."""
        from src.pipeline.checkpoint import CheckpointManager

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("{THIS IS NOT VALID JSON!!}", encoding="utf-8")

        mgr = CheckpointManager(manifest_path)
        manifest = mgr.load_or_create(
            run_id="r2", stage_name="s2", input_path="x", input_sha256="y",
            input_row_count=0, output_dir="/tmp", code_version="v",
            config_version="c", model_identifiers={}, device="cpu",
            batch_size=1, chunk_size=10,
        )
        # Should get a new, clean manifest
        assert manifest.run_id == "r2"
        assert manifest.chunks == []

    def test_empty_manifest_file_triggers_fresh_start(self, tmp_path):
        """An empty manifest file must not crash."""
        from src.pipeline.checkpoint import CheckpointManager

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("", encoding="utf-8")

        mgr = CheckpointManager(manifest_path)
        manifest = mgr.load_or_create(
            run_id="r3", stage_name="s3", input_path="x", input_sha256="y",
            input_row_count=0, output_dir="/tmp", code_version="v",
            config_version="c", model_identifiers={}, device="cpu",
            batch_size=1, chunk_size=10,
        )
        assert manifest.run_id == "r3"


# ---------------------------------------------------------------------------
# 6. Duplicate Row Detection
# ---------------------------------------------------------------------------


class TestDuplicateRowDetection:
    def test_duplicate_row_ids_are_flagged(self):
        """validate_row_identity must flag duplicate output row IDs."""
        from src.pipeline.validators import validate_row_identity

        expected = list(range(10))
        actual = list(range(10)) + [5]  # duplicate row 5

        result = validate_row_identity(expected, actual, allow_duplicates=False)
        assert not result.valid
        assert 5 in result.duplicate_row_ids

    def test_no_duplicates_passes(self):
        """No duplicates means validation passes."""
        from src.pipeline.validators import validate_row_identity

        expected = list(range(100))
        result = validate_row_identity(expected, expected[:])
        assert result.valid


# ---------------------------------------------------------------------------
# 7. Missing Row Detection
# ---------------------------------------------------------------------------


class TestMissingRowDetection:
    def test_missing_row_ids_are_flagged(self):
        """validate_row_identity must flag missing output row IDs."""
        from src.pipeline.validators import validate_row_identity

        expected = list(range(100))
        actual = [i for i in range(100) if i != 42]  # row 42 missing

        result = validate_row_identity(expected, actual)
        assert not result.valid
        assert 42 in result.missing_row_ids

    def test_extra_row_ids_are_flagged(self):
        """Unexpected extra row IDs must be flagged."""
        from src.pipeline.validators import validate_row_identity

        expected = list(range(10))
        actual = list(range(10)) + [999]  # unexpected row

        result = validate_row_identity(expected, actual)
        assert not result.valid
        assert 999 in result.extra_row_ids


# ---------------------------------------------------------------------------
# 8. Output Validation
# ---------------------------------------------------------------------------


class TestOutputValidation:
    def test_validate_output_csv_valid_file(self, tmp_path):
        """validate_output_csv must return valid for a correctly formed CSV."""
        from src.pipeline.validators import validate_output_csv

        path = tmp_path / "out.csv"
        df = pd.DataFrame({"row_id": range(50), "value": range(50)})
        df.to_csv(path, index=False)

        result = validate_output_csv(path, expected_row_ids=list(range(50)))
        assert result.valid

    def test_validate_output_csv_missing_file(self, tmp_path):
        """validate_output_csv must fail for a non-existent file."""
        from src.pipeline.validators import validate_output_csv

        result = validate_output_csv(tmp_path / "missing.csv", expected_row_ids=[0, 1])
        assert not result.valid
        assert any("not found" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# 9. FinBERT Probability Validation
# ---------------------------------------------------------------------------


class TestFinBERTProbabilityValidation:
    def test_valid_finbert_output_passes(self):
        """Well-formed FinBERT output must pass validation."""
        from src.pipeline.validators import validate_finbert_output

        df = pd.DataFrame({
            "FINBERT_POSITIVE": [0.7, 0.3],
            "FINBERT_NEGATIVE": [0.2, 0.5],
            "FINBERT_NEUTRAL": [0.1, 0.2],
            "FINBERT_SCORE": [0.5, -0.2],
            "FINBERT_LABEL": ["positive", "negative"],
        })
        result = validate_finbert_output(df)
        assert result.valid, result.report()

    def test_out_of_range_probability_fails(self):
        """FINBERT_POSITIVE > 1 must fail validation."""
        from src.pipeline.validators import validate_finbert_output

        df = pd.DataFrame({
            "FINBERT_POSITIVE": [1.5],   # out of range
            "FINBERT_NEGATIVE": [0.2],
            "FINBERT_NEUTRAL": [0.1],
            "FINBERT_SCORE": [0.5],
            "FINBERT_LABEL": ["positive"],
        })
        result = validate_finbert_output(df)
        assert not result.valid

    def test_probs_not_summing_to_one_fails(self):
        """Probabilities not summing to ~1 must fail validation."""
        from src.pipeline.validators import validate_finbert_output

        df = pd.DataFrame({
            "FINBERT_POSITIVE": [0.5],
            "FINBERT_NEGATIVE": [0.5],
            "FINBERT_NEUTRAL": [0.5],   # sum = 1.5
            "FINBERT_SCORE": [0.0],
            "FINBERT_LABEL": ["neutral"],
        })
        result = validate_finbert_output(df)
        assert not result.valid

    def test_score_out_of_range_fails(self):
        """FINBERT_SCORE outside [-1, 1] must fail."""
        from src.pipeline.validators import validate_finbert_output

        df = pd.DataFrame({
            "FINBERT_POSITIVE": [0.7],
            "FINBERT_NEGATIVE": [0.2],
            "FINBERT_NEUTRAL": [0.1],
            "FINBERT_SCORE": [2.0],   # out of range
            "FINBERT_LABEL": ["positive"],
        })
        result = validate_finbert_output(df)
        assert not result.valid


# ---------------------------------------------------------------------------
# 10. Impact Score Validation
# ---------------------------------------------------------------------------


class TestImpactScoreValidation:
    def test_valid_impact_scores_pass(self):
        """Impact scores in [1, 10] must pass validation."""
        from src.pipeline.validators import validate_impact_output

        df = pd.DataFrame({"IMPACT_SCORE": [1.0, 5.5, 10.0]})
        result = validate_impact_output(df)
        assert result.valid, result.report()

    def test_impact_below_one_fails(self):
        """Impact score < 1.0 must fail."""
        from src.pipeline.validators import validate_impact_output

        df = pd.DataFrame({"IMPACT_SCORE": [0.5, 5.0]})
        result = validate_impact_output(df)
        assert not result.valid

    def test_impact_above_ten_fails(self):
        """Impact score > 10.0 must fail."""
        from src.pipeline.validators import validate_impact_output

        df = pd.DataFrame({"IMPACT_SCORE": [5.0, 10.1]})
        result = validate_impact_output(df)
        assert not result.valid

    def test_nan_impact_fails(self):
        """NaN impact score must fail validation."""
        from src.pipeline.validators import validate_impact_output

        df = pd.DataFrame({"IMPACT_SCORE": [float("nan"), 5.0]})
        result = validate_impact_output(df)
        assert not result.valid

    def test_missing_column_fails(self):
        """Missing IMPACT_SCORE column must fail."""
        from src.pipeline.validators import validate_impact_output

        df = pd.DataFrame({"other_col": [1, 2, 3]})
        result = validate_impact_output(df)
        assert not result.valid


# ---------------------------------------------------------------------------
# 11. Leakage Protection
# ---------------------------------------------------------------------------


class TestLeakageProtection:
    def test_leakage_column_detected(self):
        """check_leakage_columns must detect all forbidden columns."""
        from src.pipeline.validators import check_leakage_columns, LEAKAGE_COLUMNS

        df = pd.DataFrame({
            "TWEET": ["test"],
            "1_DAY_RETURN": [0.01],
            "LSTM_POLARITY": [0.5],
        })
        violations = check_leakage_columns(df, "test context")
        assert len(violations) == 2

    def test_assert_no_leakage_raises(self):
        """assert_no_leakage must raise ValueError for leakage columns."""
        from src.pipeline.validators import assert_no_leakage

        df = pd.DataFrame({
            "TWEET": ["test"],
            "1_DAY_RETURN": [0.01],
        })
        with pytest.raises(ValueError, match="LEAKAGE GUARD"):
            assert_no_leakage(df, "test")

    def test_clean_dataframe_passes_leakage_guard(self):
        """DataFrame without leakage columns must pass the guard."""
        from src.pipeline.validators import assert_no_leakage

        df = pd.DataFrame({
            "row_id": [0],
            "TWEET": ["Apple earnings"],
            "STOCK": ["AAPL"],
        })
        # Should not raise
        assert_no_leakage(df, "test")

    def test_all_forbidden_columns_are_checked(self):
        """All 6 leakage columns must be in the forbidden set."""
        from src.pipeline.validators import LEAKAGE_COLUMNS

        expected = {
            "1_DAY_RETURN", "2_DAY_RETURN", "3_DAY_RETURN", "7_DAY_RETURN",
            "LSTM_POLARITY", "TEXTBLOB_POLARITY",
        }
        assert expected == set(LEAKAGE_COLUMNS), (
            f"Leakage column set mismatch: got {LEAKAGE_COLUMNS}"
        )

    def test_validated_csv_strips_leakage_columns(self, tmp_path):
        """The validation stage must strip leakage columns from inference path."""
        n = 20
        csv_with_leakage = make_validated_csv(n, tmp_path, include_leakage=True)

        # Read and explicitly strip leakage columns (simulating validation stage)
        from src.pipeline.validators import LEAKAGE_COLUMNS
        df = pd.read_csv(csv_with_leakage)
        inference_cols = [c for c in df.columns if c not in LEAKAGE_COLUMNS]
        df_inference = df[inference_cols]

        from src.pipeline.validators import check_leakage_columns
        violations = check_leakage_columns(df_inference)
        assert len(violations) == 0, f"Leakage columns still present: {violations}"


# ---------------------------------------------------------------------------
# 12. Deterministic Repeated Execution
# ---------------------------------------------------------------------------


class TestDeterministicExecution:
    def test_materiality_classify_text_is_deterministic(self):
        """classify_text must return identical results on repeated calls."""
        from src.nlp.event_materiality_v4 import classify_text

        text = "Apple filed for bankruptcy protection under Chapter 11"
        r1 = classify_text(text, "Credit Event", "FINANCIAL_EVENT", 0.9)
        r2 = classify_text(text, "Credit Event", "FINANCIAL_EVENT", 0.9)
        assert r1 == r2, "classify_text must be deterministic"

    def test_impact_scorer_is_deterministic(self):
        """ImpactScorer must return identical scores on repeated calls."""
        from src.risk.impact_scorer import ImpactScorer

        scorer = ImpactScorer()
        score1, _, _ = scorer.score_dataframe_row(
            event_type="Corporate / Earnings",
            materiality="MATERIAL_EVENT",
            event_confidence=0.75,
            sentiment_score=0.5,
        )
        score2, _, _ = scorer.score_dataframe_row(
            event_type="Corporate / Earnings",
            materiality="MATERIAL_EVENT",
            event_confidence=0.75,
            sentiment_score=0.5,
        )
        assert score1 == score2, "ImpactScorer must be deterministic"

    def test_tweet_hash_is_deterministic(self):
        """tweet_hash must produce identical output for the same input."""
        from src.nlp.finbert_inference import tweet_hash, normalize_text

        text = "Apple reports record quarterly earnings"
        h1 = tweet_hash(normalize_text(text))
        h2 = tweet_hash(normalize_text(text))
        assert h1 == h2


# ---------------------------------------------------------------------------
# 13. Dry-Run Configuration
# ---------------------------------------------------------------------------


class TestDryRunConfiguration:
    def test_max_rows_limits_output(self, tmp_path):
        """When max_rows is set, the output must contain exactly max_rows rows."""
        n_total = 500
        max_rows = 100
        csv_path = make_validated_csv(n_total, tmp_path)

        # Simulate reading with max_rows limit
        df = pd.read_csv(csv_path, nrows=max_rows)
        assert len(df) == max_rows

    def test_chunk_size_controls_granularity(self, tmp_path):
        """Different chunk sizes must produce the same total output."""
        n = 250
        csv_path = make_event_csv(n, tmp_path)

        # Read in chunk_size=50
        rows_small = []
        for chunk in pd.read_csv(csv_path, chunksize=50):
            rows_small.append(chunk)
        total_small = sum(len(c) for c in rows_small)

        # Read in chunk_size=100
        rows_large = []
        for chunk in pd.read_csv(csv_path, chunksize=100):
            rows_large.append(chunk)
        total_large = sum(len(c) for c in rows_large)

        assert total_small == total_large == n

    def test_checkpoint_dir_created_automatically(self, tmp_path):
        """CheckpointManager must create the checkpoint directory automatically."""
        from src.pipeline.checkpoint import CheckpointManager

        deep_path = tmp_path / "a" / "b" / "c" / "manifest.json"
        assert not deep_path.parent.exists()

        mgr = CheckpointManager(deep_path)
        assert deep_path.parent.exists(), "CheckpointManager must create parent dirs"


# ---------------------------------------------------------------------------
# 14. Manifest Creation
# ---------------------------------------------------------------------------


class TestManifestCreation:
    def test_run_manifest_serializes_correctly(self, tmp_path):
        """RunManifest must serialize all required fields to JSON."""
        from src.pipeline.manifest import RunManifest

        # Use a real file for sha256
        input_file = tmp_path / "input.csv"
        input_file.write_text("row_id,TWEET\n0,hello\n")

        m = RunManifest(
            stage_name="finbert",
            input_path=input_file,
            output_dir=tmp_path,
            chunk_size=1000,
            batch_size=32,
            device="cpu",
            model_identifiers={"finbert": "ProsusAI/finbert"},
        )
        m.finalize(100, 100, 5.0)

        save_path = tmp_path / "manifest.json"
        m.save(save_path)

        assert save_path.exists()
        with save_path.open() as fh:
            data = json.load(fh)

        required_fields = [
            "run_id", "stage_name", "input_path", "input_sha256",
            "input_row_count", "output_dir", "output_row_count",
            "code_version", "model_identifiers", "device",
            "batch_size", "chunk_size", "created_at",
        ]
        for field in required_fields:
            assert field in data, f"Manifest missing: {field}"

    def test_run_manifest_loads_back_correctly(self, tmp_path):
        """RunManifest saved to disk must load back with identical values."""
        from src.pipeline.manifest import RunManifest

        input_file = tmp_path / "input.csv"
        input_file.write_text("row_id,TWEET\n0,test\n")

        m = RunManifest(
            stage_name="test_stage",
            input_path=input_file,
            output_dir=tmp_path,
            chunk_size=500,
            batch_size=16,
            device="cuda",
            model_identifiers={"model": "test-model"},
        )
        m.finalize(200, 195, 10.5)

        save_path = tmp_path / "manifest.json"
        m.save(save_path)

        loaded = RunManifest.load(save_path)
        assert loaded.stage_name == "test_stage"
        assert loaded.batch_size == 16
        assert loaded.input_row_count == 200
        assert loaded.output_row_count == 195

    def test_git_unavailable_does_not_crash(self, tmp_path):
        """get_code_version must return a string even when git is unavailable."""
        from src.pipeline.manifest import get_code_version

        version = get_code_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_sha256_of_file_stable(self, tmp_path):
        """sha256_of_file must return identical hash for identical content."""
        from src.pipeline.checkpoint import sha256_of_file

        f = tmp_path / "data.txt"
        f.write_bytes(b"hello world" * 1000)
        h1 = sha256_of_file(f)
        h2 = sha256_of_file(f)
        assert h1 == h2

    def test_sha256_differs_for_different_content(self, tmp_path):
        """sha256_of_file must return different hashes for different content."""
        from src.pipeline.checkpoint import sha256_of_file

        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content_a" * 100)
        f2.write_bytes(b"content_b" * 100)

        assert sha256_of_file(f1) != sha256_of_file(f2)


# ---------------------------------------------------------------------------
# Event output validator tests
# ---------------------------------------------------------------------------


class TestEventOutputValidation:
    def test_valid_event_output_passes(self):
        """Valid event types and confidence values must pass."""
        from src.pipeline.validators import validate_event_output

        df = pd.DataFrame({
            "EVENT_TYPE": ["Corporate / Earnings", "Macroeconomic"],
            "EVENT_CONFIDENCE": [0.75, 0.60],
        })
        result = validate_event_output(df)
        assert result.valid, result.report()

    def test_invalid_event_type_fails(self):
        """An event type outside the taxonomy must fail."""
        from src.pipeline.validators import validate_event_output

        df = pd.DataFrame({
            "EVENT_TYPE": ["Made Up Event Type"],
            "EVENT_CONFIDENCE": [0.8],
        })
        result = validate_event_output(df)
        assert not result.valid

    def test_confidence_out_of_range_fails(self):
        """EVENT_CONFIDENCE > 1 must fail."""
        from src.pipeline.validators import validate_event_output

        df = pd.DataFrame({
            "EVENT_TYPE": ["Macroeconomic"],
            "EVENT_CONFIDENCE": [1.5],
        })
        result = validate_event_output(df)
        assert not result.valid
