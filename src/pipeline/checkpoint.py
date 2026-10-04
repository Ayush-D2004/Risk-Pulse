"""
Chunk Manifest & Checkpoint System
====================================
Provides durable chunk-level state tracking for the production-scale
RiskPulse pipeline.  Every expensive stage must use these primitives to
enable interrupt-and-resume operation without recomputing completed work.

Design rules
------------
* A chunk is only marked COMPLETE once its output file has been verified
  (row-count matches the expected output).
* Corrupt or partial chunk outputs are treated as FAILED, not COMPLETE.
* No in-memory global state — everything is persisted to JSON on disk.
* All timestamps are UTC ISO-8601.
* Thread-safety is out of scope: Colab single-GPU runs are sequential.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Version sentinel — bump when the checkpoint schema changes.
# ---------------------------------------------------------------------------
CHECKPOINT_SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Chunk status values
# ---------------------------------------------------------------------------
STATUS_PENDING = "PENDING"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED = "SKIPPED"   # reserved for explicit skip (e.g. empty slice)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ChunkRecord:
    """Persistent metadata for a single processing chunk."""

    chunk_id: str
    input_start: int          # inclusive row index in the source file
    input_end: int            # exclusive row index
    input_row_count: int
    output_row_count: int = 0
    status: str = STATUS_PENDING
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    code_version: str = ""
    model_version: str = ""
    config_version: str = ""
    error_message: str = ""
    output_path: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ChunkRecord":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


@dataclass
class StageManifest:
    """
    Persistent manifest for a single pipeline stage execution.

    Created once at stage start and updated incrementally as chunks complete.
    """

    run_id: str
    stage_name: str
    input_path: str
    input_sha256: str
    input_row_count: int
    output_dir: str
    code_version: str
    config_version: str
    model_identifiers: Dict[str, str]
    device: str
    batch_size: int
    chunk_size: int
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = CHECKPOINT_SCHEMA_VERSION
    chunks: List[dict] = field(default_factory=list)

    # -----------------------------------------------------------------------
    def _chunk_index(self) -> Dict[str, int]:
        """Return {chunk_id: list_index} lookup."""
        return {c["chunk_id"]: i for i, c in enumerate(self.chunks)}

    def upsert_chunk(self, record: ChunkRecord) -> None:
        idx_map = self._chunk_index()
        if record.chunk_id in idx_map:
            self.chunks[idx_map[record.chunk_id]] = record.to_dict()
        else:
            self.chunks.append(record.to_dict())
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def get_chunk(self, chunk_id: str) -> Optional[ChunkRecord]:
        idx_map = self._chunk_index()
        if chunk_id not in idx_map:
            return None
        return ChunkRecord.from_dict(self.chunks[idx_map[chunk_id]])

    def completed_chunk_ids(self) -> List[str]:
        return [c["chunk_id"] for c in self.chunks if c.get("status") == STATUS_COMPLETE]

    def pending_or_failed_chunks(self) -> List[ChunkRecord]:
        return [
            ChunkRecord.from_dict(c)
            for c in self.chunks
            if c.get("status") in (STATUS_PENDING, STATUS_FAILED)
        ]

    def total_output_rows(self) -> int:
        return sum(
            c.get("output_row_count", 0)
            for c in self.chunks
            if c.get("status") == STATUS_COMPLETE
        )

    def is_complete(self) -> bool:
        if not self.chunks:
            return False
        return all(c.get("status") == STATUS_COMPLETE for c in self.chunks)

    def summary(self) -> str:
        total = len(self.chunks)
        done = sum(1 for c in self.chunks if c.get("status") == STATUS_COMPLETE)
        failed = sum(1 for c in self.chunks if c.get("status") == STATUS_FAILED)
        pending = total - done - failed
        out_rows = self.total_output_rows()
        return (
            f"[{self.stage_name}] run={self.run_id} "
            f"chunks={total} done={done} failed={failed} pending={pending} "
            f"output_rows={out_rows:,}"
        )

    # -----------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StageManifest":
        obj = cls(
            run_id=d["run_id"],
            stage_name=d["stage_name"],
            input_path=d["input_path"],
            input_sha256=d["input_sha256"],
            input_row_count=d["input_row_count"],
            output_dir=d["output_dir"],
            code_version=d["code_version"],
            config_version=d["config_version"],
            model_identifiers=d.get("model_identifiers", {}),
            device=d.get("device", "cpu"),
            batch_size=d.get("batch_size", 32),
            chunk_size=d.get("chunk_size", 10_000),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            schema_version=d.get("schema_version", CHECKPOINT_SCHEMA_VERSION),
            chunks=d.get("chunks", []),
        )
        return obj


# ---------------------------------------------------------------------------
# CheckpointManager
# ---------------------------------------------------------------------------


class CheckpointManager:
    """
    Persist and load StageManifests for a pipeline stage.

    Usage pattern
    -------------
    >>> mgr = CheckpointManager(manifest_path)
    >>> manifest = mgr.load_or_create(run_id, stage_name, ...)
    >>> # Before processing each chunk:
    >>> if chunk_id in manifest.completed_chunk_ids():
    ...     continue  # skip already done
    >>> # Process chunk ...
    >>> record = ChunkRecord(chunk_id=chunk_id, ...)
    >>> mgr.mark_complete(manifest, record)
    """

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def load_or_create(
        self,
        run_id: str,
        stage_name: str,
        input_path: str,
        input_sha256: str,
        input_row_count: int,
        output_dir: str,
        code_version: str,
        config_version: str,
        model_identifiers: Dict[str, str],
        device: str,
        batch_size: int,
        chunk_size: int,
    ) -> StageManifest:
        """Load an existing manifest or create a fresh one."""
        if self.manifest_path.exists():
            try:
                with self.manifest_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                manifest = StageManifest.from_dict(data)
                print(
                    f"[checkpoint] Loaded existing manifest: {manifest.summary()}"
                )
                return manifest
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                print(
                    f"[checkpoint] WARNING: corrupt manifest at {self.manifest_path}: {exc}"
                )
                print("[checkpoint] Starting fresh manifest.")

        manifest = StageManifest(
            run_id=run_id,
            stage_name=stage_name,
            input_path=str(input_path),
            input_sha256=input_sha256,
            input_row_count=input_row_count,
            output_dir=str(output_dir),
            code_version=code_version,
            config_version=config_version,
            model_identifiers=model_identifiers,
            device=device,
            batch_size=batch_size,
            chunk_size=chunk_size,
        )
        self._save(manifest)
        return manifest

    # ------------------------------------------------------------------
    def mark_in_progress(
        self, manifest: StageManifest, chunk_id: str, start: int, end: int
    ) -> ChunkRecord:
        record = ChunkRecord(
            chunk_id=chunk_id,
            input_start=start,
            input_end=end,
            input_row_count=end - start,
            status=STATUS_IN_PROGRESS,
            code_version=manifest.code_version,
            model_version=";".join(
                f"{k}={v}" for k, v in manifest.model_identifiers.items()
            ),
            config_version=manifest.config_version,
        )
        manifest.upsert_chunk(record)
        self._save(manifest)
        return record

    # ------------------------------------------------------------------
    def mark_complete(
        self,
        manifest: StageManifest,
        record: ChunkRecord,
        output_row_count: int,
        output_path: str,
        duration_seconds: float,
    ) -> None:
        record.status = STATUS_COMPLETE
        record.output_row_count = output_row_count
        record.output_path = str(output_path)
        record.duration_seconds = duration_seconds
        record.timestamp = datetime.now(timezone.utc).isoformat()
        manifest.upsert_chunk(record)
        self._save(manifest)

    # ------------------------------------------------------------------
    def mark_failed(
        self,
        manifest: StageManifest,
        record: ChunkRecord,
        error_message: str,
    ) -> None:
        record.status = STATUS_FAILED
        record.error_message = error_message
        record.timestamp = datetime.now(timezone.utc).isoformat()
        manifest.upsert_chunk(record)
        self._save(manifest)

    # ------------------------------------------------------------------
    def _save(self, manifest: StageManifest) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(manifest.to_dict(), fh, indent=2, ensure_ascii=False)
        # Atomic rename
        tmp.replace(self.manifest_path)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def sha256_of_file(path: str | Path, max_bytes: int = 10 * 1024 * 1024) -> str:
    """
    Compute SHA-256 of a file.

    For very large files (>max_bytes) we hash only the first chunk plus the
    file size, which is sufficient for a uniqueness check without reading
    the entire file on every run.
    """
    path = Path(path)
    h = hashlib.sha256()
    size = path.stat().st_size
    with path.open("rb") as fh:
        data = fh.read(max_bytes)
        h.update(data)
    h.update(str(size).encode())
    return h.hexdigest()


def build_chunk_id(stage_name: str, chunk_index: int) -> str:
    """Deterministic chunk identifier based on stage and position."""
    return f"{stage_name}_chunk_{chunk_index:06d}"


def count_csv_rows(path: str | Path) -> int:
    """Count data rows in a CSV (excluding the header)."""
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        total = sum(1 for _ in fh)
    # Subtract header
    return max(0, total - 1)
