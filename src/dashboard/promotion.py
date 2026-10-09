from typing import Dict, List, Optional
from pydantic import BaseModel
import time

from src.integration.runtime_models import PipelineRun, RunStatus, RunMode
from src.risk.risk_signal import RiskSignal
from src.portfolio.orchestration_models import StressScenarioResult

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
    def __init__(self):
        self.promoted_runs: Dict[str, PromotedRun] = {}
        self.signals: Dict[str, RiskSignal] = {}
        self.results: Dict[str, StressScenarioResult] = {}
        self.provenance_map: Dict[str, str] = {}

    def promote(self, run: PipelineRun, existing_event_ids: frozenset) -> PromotedRunResponse:
        if run.status != RunStatus.COMPLETED:
            raise ValueError("Run must be COMPLETED")
        if not run.final_result or "signals" not in run.final_result or "stress_results" not in run.final_result:
            raise ValueError("Run is missing valid final_result")

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
            if eid in self.results:
                raise ValueError(f"Collision with another promoted run for event: {eid}")

        for sig, res in zip(signals, stress_results):
            if sig.event_id != res.event_id:
                raise ValueError(f"Mismatched event ID in signal vs result: {sig.event_id} != {res.event_id}")
            self.signals[sig.event_id] = sig
            self.results[sig.event_id] = res
            self.provenance_map[sig.event_id] = run.request.mode.value

        source = run.request.observations[0].source.value if run.request.observations else None
        channel = run.request.observations[0].channel.value if run.request.observations and run.request.observations[0].channel else None

        promoted = PromotedRun(
            run_id=run.run_id,
            mode=run.request.mode,
            source=source,
            channel=channel,
            promoted_at=time.time(),
            event_ids=event_ids
        )
        self.promoted_runs[run.run_id] = promoted

        return PromotedRunResponse(
            run_id=run.run_id,
            status="SUCCESS",
            promoted_event_ids=event_ids,
            count=len(event_ids)
        )
