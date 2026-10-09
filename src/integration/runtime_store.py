import json
from typing import Dict, List, Optional
from .runtime_models import PipelineRun, RunStatus
from src.db import DatabaseLayer, db_instance

class RuntimeStore:
    def __init__(self, db: Optional[DatabaseLayer] = None):
        self.db = db or db_instance
        self._recover_interrupted_runs()

    def _recover_interrupted_runs(self):
        conn = self.db._get_conn()
        with conn:
            # Mark runs that were left in PENDING/RUNNING state as FAILED
            conn.execute(
                "UPDATE pipeline_runs SET status = ? WHERE status IN (?, ?)",
                (RunStatus.FAILED.value, RunStatus.PENDING.value, RunStatus.RUNNING.value)
            )
            # Update the JSON payload status so it's consistent
            # We fetch those runs, modify the JSON, and write back
            c = conn.execute("SELECT run_id, payload FROM pipeline_runs WHERE status = ?", (RunStatus.FAILED.value,))
            rows = c.fetchall()
            for row in rows:
                run_id, payload_str = row
                try:
                    payload = json.loads(payload_str)
                    if payload.get("status") in (RunStatus.PENDING.value, RunStatus.RUNNING.value):
                        payload["status"] = RunStatus.FAILED.value
                        if not payload.get("error"):
                            payload["error"] = "Run interrupted by system restart."
                        conn.execute(
                            "UPDATE pipeline_runs SET payload = ? WHERE run_id = ?",
                            (json.dumps(payload), run_id)
                        )
                except json.JSONDecodeError:
                    pass

    def add_run(self, run: PipelineRun):
        self.update_run(run)

    def update_run(self, run: PipelineRun):
        conn = self.db._get_conn()
        with conn:
            conn.execute(
                """
                INSERT INTO pipeline_runs (run_id, status, created_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    payload=excluded.payload
                """,
                (run.run_id, run.status.value, run.created_at.isoformat(), run.model_dump_json())
            )

    def get_run(self, run_id: str) -> Optional[PipelineRun]:
        conn = self.db._get_conn()
        c = conn.execute("SELECT payload FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = c.fetchone()
        if not row:
            return None
        return PipelineRun.model_validate_json(row[0])

    def get_all_runs(self) -> List[PipelineRun]:
        conn = self.db._get_conn()
        c = conn.execute("SELECT payload FROM pipeline_runs ORDER BY created_at DESC")
        return [PipelineRun.model_validate_json(row[0]) for row in c.fetchall()]

    def get_active_runs(self) -> List[PipelineRun]:
        conn = self.db._get_conn()
        c = conn.execute(
            "SELECT payload FROM pipeline_runs WHERE status IN (?, ?) ORDER BY created_at ASC",
            (RunStatus.PENDING.value, RunStatus.RUNNING.value)
        )
        return [PipelineRun.model_validate_json(row[0]) for row in c.fetchall()]
