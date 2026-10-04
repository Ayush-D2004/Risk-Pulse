"""
Processing Run Manifest
=========================
Lightweight reproducibility record for a complete pipeline run.

Required fields per the Step 18 specification:
    run_id
    input_path
    input_sha256
    input_row_count
    code_version
    config_version
    model_identifiers
    model_revision  (if available)
    device
    batch_size
    chunk_size
    created_at
"""

from __future__ import annotations

import json
import os
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.pipeline.checkpoint import sha256_of_file


# ---------------------------------------------------------------------------
# Version resolution helpers
# ---------------------------------------------------------------------------

def _git_short_hash() -> str:
    """
    Attempt to read the current Git HEAD hash.

    Returns a human-readable fallback string if Git metadata is not accessible
    (e.g., running in Google Colab from a ZIP, or in an untracked directory).
    We do NOT claim a git hash exists when it doesn't.
    """
    try:
        git_head = Path(".git/HEAD")
        if not git_head.exists():
            return "git_unavailable"
        ref = git_head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref: "):
            ref_file = Path(".git") / ref[5:]
            if ref_file.exists():
                return ref_file.read_text(encoding="utf-8").strip()[:8]
            return "detached_head"
        # Detached HEAD — return the hash directly
        return ref[:8]
    except Exception:
        return "git_unavailable"


def _python_version() -> str:
    return f"py{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _torch_version() -> str:
    try:
        import torch
        return f"torch{torch.__version__}"
    except ImportError:
        return "torch_not_installed"


def _transformers_version() -> str:
    try:
        import transformers
        return transformers.__version__
    except ImportError:
        return "transformers_not_installed"


def get_code_version() -> str:
    """
    Return a composite version string: git_hash:python_version:torch_version
    """
    return f"{_git_short_hash()}:{_python_version()}:{_torch_version()}"


# ---------------------------------------------------------------------------
# Run Manifest
# ---------------------------------------------------------------------------


class RunManifest:
    """
    Reproducibility manifest for a pipeline stage run.

    Create at the start of every large processing run.  The manifest is
    serialized to JSON alongside stage outputs so future runs can verify the
    exact conditions under which each output was produced.
    """

    def __init__(
        self,
        stage_name: str,
        input_path: str | Path,
        output_dir: str | Path,
        chunk_size: int,
        batch_size: int,
        device: str,
        model_identifiers: Optional[Dict[str, str]] = None,
        config_version: str = "v1",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.run_id = uuid.uuid4().hex
        self.stage_name = stage_name
        self.input_path = str(input_path)
        self.output_dir = str(output_dir)
        self.chunk_size = chunk_size
        self.batch_size = batch_size
        self.device = device
        self.model_identifiers: Dict[str, str] = model_identifiers or {}
        self.config_version = config_version
        self.code_version = get_code_version()
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.extra: Dict[str, Any] = extra or {}

        # Compute input file metadata (only if the file exists)
        input_file = Path(input_path)
        if input_file.exists():
            self.input_sha256 = sha256_of_file(input_file)
            self.input_file_size_bytes = input_file.stat().st_size
        else:
            self.input_sha256 = "file_not_found"
            self.input_file_size_bytes = 0

        # Capture runtime environment
        self.python_version = _python_version()
        self.torch_version = _torch_version()
        self.transformers_version = _transformers_version()
        self.platform = platform.platform()
        self.hostname = platform.node()

        # Capture GPU metadata if torch is available
        self.cuda_available = False
        self.gpu_name = "N/A"
        try:
            import torch
            self.cuda_available = torch.cuda.is_available()
            if self.cuda_available and self.device.startswith("cuda"):
                # Handle cases like "cuda:0" or just "cuda"
                dev_idx = 0
                if ":" in self.device:
                    try:
                        dev_idx = int(self.device.split(":")[1])
                    except ValueError:
                        pass
                self.gpu_name = torch.cuda.get_device_name(dev_idx)
        except ImportError:
            pass

        # Will be populated after the run
        self.input_row_count: int = 0
        self.output_row_count: int = 0
        self.completed_at: Optional[str] = None
        self.duration_seconds: Optional[float] = None

    # ------------------------------------------------------------------

    def finalize(self, input_row_count: int, output_row_count: int, duration_seconds: float) -> None:
        """Mark the run as complete with final metrics."""
        self.input_row_count = input_row_count
        self.output_row_count = output_row_count
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.duration_seconds = duration_seconds

    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stage_name": self.stage_name,
            "input_path": self.input_path,
            "input_sha256": self.input_sha256,
            "input_file_size_bytes": self.input_file_size_bytes,
            "input_row_count": self.input_row_count,
            "output_dir": self.output_dir,
            "output_row_count": self.output_row_count,
            "code_version": self.code_version,
            "config_version": self.config_version,
            "model_identifiers": self.model_identifiers,
            "device": self.device,
            "batch_size": self.batch_size,
            "chunk_size": self.chunk_size,
            "python_version": self.python_version,
            "torch_version": self.torch_version,
            "transformers_version": self.transformers_version,
            "cuda_available": getattr(self, "cuda_available", False),
            "gpu_name": getattr(self, "gpu_name", "N/A"),
            "platform": self.platform,
            "hostname": self.hostname,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            **self.extra,
        }

    def save(self, path: str | Path) -> None:
        """Persist the manifest to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str | Path) -> "RunManifest":
        """Load a manifest from a JSON file (read-only / audit purposes)."""
        with Path(path).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        obj = object.__new__(cls)
        for k, v in data.items():
            setattr(obj, k, v)
        return obj

    def __repr__(self) -> str:
        return (
            f"RunManifest(run_id={self.run_id!r}, stage={self.stage_name!r}, "
            f"input_rows={self.input_row_count:,}, device={self.device!r})"
        )
