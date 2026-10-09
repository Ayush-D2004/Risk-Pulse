import json
import time
from typing import Dict, List, Optional
from pydantic import BaseModel
import sqlite3

from src.integration.runtime_models import PipelineRun, RunStatus, RunMode
from src.risk.risk_signal import RiskSignal
from src.portfolio.orchestration_models import StressScenarioResult
from src.db import DatabaseLayer, db_instance

class PromotedRunResponse(BaseModel):
    run_id: str
    status: str
    promoted_event_ids: List[str]
    count: int

class PromotedRun(BaseModel):
    run_id: str
    mode: RunMode
    source: Optional[str]
    channel: Optional[str]
    promoted_at: float
    event_ids: List[str]

class PromotionRegistry:
    def __init__(self, db: Optional[DatabaseLayer] = None):
        self.db = db or db_instance
        # The dictionaries are kept as read models to serve api.py quickly,
        # but they are populated from the DB on startup.
        self.promoted_runs: Dict[str, PromotedRun] = {}
        self.signals: Dict[str, RiskSignal] = {}
        self.results: Dict[str, StressScenarioResult] = {}
        self.provenance_map: Dict[str, str] = {}
        self._load_from_db()

    def _load_from_db(self):
        conn = self.db._get_conn()
        with conn:
            c = conn.execute("SELECT * FROM promoted_runs")
            for row in c.fetchall():
                event_ids = json.loads(row["event_ids_json"])
                self.promoted_runs[row["run_id"]] = PromotedRun(
                    run_id=row["run_id"],
                    mode=RunMode(row["mode"]),
                    source=row["source"],
                    channel=row["channel"],
                    promoted_at=row["promoted_at"],
                    event_ids=event_ids
                )
            
            c = conn.execute("SELECT * FROM promoted_events")
            for row in c.fetchall():
                eid = row["event_id"]
                self.signals[eid] = RiskSignal.model_validate_json(row["signal_payload"])
                self.results[eid] = StressScenarioResult.model_validate_json(row["result_payload"])
                self.provenance_map[eid] = row["provenance"]

    def promote(self, run: PipelineRun, existing_event_ids: frozenset) -> PromotedRunResponse:
        if run.status != RunStatus.COMPLETED:
            raise ValueError("Run must be COMPLETED")
        if not run.final_result or "signals" not in run.final_result or "stress_results" not in run.final_result:
            raise ValueError("Run is missing valid final_result")

        # Idempotency check in memory (backed by DB)
        if run.run_id in self.promoted_runs:
            return PromotedRunResponse(
                run_id=run.run_id,
                status="ALREADY_PROMOTED",
                promoted_event_ids=self.promoted_runs[run.run_id].event_ids,
                count=len(self.promoted_runs[run.run_id].event_ids)
            )

        signals = [RiskSignal(**s) for s in run.final_result["signals"]]
        stress_results = [StressScenarioResult(**r) for r in run.final_result["stress_results"]]

        if len(signals) != len(stress_results):
            raise ValueError("Mismatched signals and stress results")

        event_ids = [s.event_id for s in signals]

        for eid in event_ids:
            if eid in existing_event_ids:
                raise ValueError(f"Collision with demo fixture: {eid}")
            if eid in self.results and run.run_id not in self.promoted_runs:
                # If event already promoted in another run
                other_run = self.provenance_map.get(eid)
                if other_run != run.request.mode.value:
                    raise ValueError(f"Collision with another promoted run for event: {eid}")

        for sig, res in zip(signals, stress_results):
            if sig.event_id != res.event_id:
                raise ValueError(f"Mismatched event ID in signal vs result: {sig.event_id} != {res.event_id}")

        source = run.request.observations[0].source.value if run.request.observations else None
        channel = run.request.observations[0].channel.value if run.request.observations and run.request.observations[0].channel else None
        promoted_at = time.time()

        conn = self.db._get_conn()
        try:
            with conn: # transaction begins
                # 1. Insert into promoted_runs
                conn.execute(
                    """
                    INSERT OR REPLACE INTO promoted_runs (run_id, mode, source, channel, promoted_at, event_ids_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (run.run_id, run.request.mode.value, source, channel, promoted_at, json.dumps(event_ids))
                )
                
                # 2. Insert into promoted_events
                for sig, res in zip(signals, stress_results):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO promoted_events (event_id, run_id, signal_payload, result_payload, provenance)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (sig.event_id, run.run_id, sig.model_dump_json(), res.model_dump_json(), run.request.mode.value)
                    )
        except sqlite3.IntegrityError as e:
            # Handle duplicate or already-promoted events cleanly
            if "UNIQUE constraint failed" in str(e):
                return PromotedRunResponse(
                    run_id=run.run_id,
                    status="ALREADY_PROMOTED",
                    promoted_event_ids=event_ids,
                    count=len(event_ids)
                )
            raise ValueError(f"Database integrity error: {e}")

        # Update in-memory read models only if transaction succeeded
        for sig, res in zip(signals, stress_results):
            self.signals[sig.event_id] = sig
            self.results[sig.event_id] = res
            self.provenance_map[sig.event_id] = run.request.mode.value

        self.promoted_runs[run.run_id] = PromotedRun(
            run_id=run.run_id,
            mode=run.request.mode,
            source=source,
            channel=channel,
            promoted_at=promoted_at,
            event_ids=event_ids
        )

        return PromotedRunResponse(
            run_id=run.run_id,
            status="SUCCESS",
            promoted_event_ids=event_ids,
            count=len(event_ids)
        )
