from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class RunMode(str, Enum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    LIVE_GDELT = "LIVE_GDELT"
    ANALYST_SIMULATION = "ANALYST_SIMULATION"
    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"

class ObservationSource(str, Enum):
    GDELT = "GDELT"
    HISTORICAL_SOCIAL = "HISTORICAL_SOCIAL"
    ANALYST_SIMULATION = "ANALYST_SIMULATION"
    OTHER = "OTHER"

class AnalystChannel(str, Enum):
    TWITTER_X_STYLE = "TWITTER_X_STYLE"
    NEWS = "NEWS"

class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class PipelineStage(BaseModel):
    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    output: Optional[Dict[str, Any]] = None

class ObservationInput(BaseModel):
    text: str
    headline: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    entity: Optional[str] = None
    source: ObservationSource = ObservationSource.OTHER
    timestamp: Optional[datetime] = None
    channel: Optional[AnalystChannel] = None
    metadata: Optional[Dict[str, Any]] = None

class PipelineRunRequest(BaseModel):
    mode: RunMode = RunMode.ANALYST_SIMULATION
    observations: List[ObservationInput]

PIPELINE_STAGE_NAMES: List[str] = [
    "ingestion",
    "preprocessing",
    "entity_resolution",
    "sentiment",
    "event_classification",
    "materiality",
    "impact",
    "clustering",
    "market_context",
    "portfolio_stress",
]

def create_initial_pipeline_stages() -> List[PipelineStage]:
    return [PipelineStage(name=name, status=StageStatus.PENDING) for name in PIPELINE_STAGE_NAMES]

class PipelineRun(BaseModel):
    run_id: str
    status: RunStatus = RunStatus.PENDING
    request: PipelineRunRequest
    stages: List[PipelineStage] = Field(default_factory=create_initial_pipeline_stages)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    final_result: Optional[Dict[str, Any]] = None
