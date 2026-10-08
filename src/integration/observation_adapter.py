from pydantic import BaseModel
from typing import Optional, List
from .runtime_models import PipelineRunRequest, RunMode, ObservationSource, ObservationInput

class NewsDocument(BaseModel):
    text: str
    headline: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = "news"
    target_entity: Optional[str] = None

def adapt_to_run_request(docs: List[NewsDocument], mode: RunMode = RunMode.ANALYST_SIMULATION) -> PipelineRunRequest:
    observations = []
    for doc in docs:
        source_enum = ObservationSource.OTHER
        if doc.source == "GDELT":
            source_enum = ObservationSource.GDELT
        elif doc.source == "HISTORICAL_SOCIAL":
            source_enum = ObservationSource.HISTORICAL_SOCIAL
        elif doc.source == "ANALYST_SIMULATION":
            source_enum = ObservationSource.ANALYST_SIMULATION
            
        observations.append(ObservationInput(
            text=doc.text,
            headline=doc.headline,
            url=doc.url,
            entity=doc.target_entity,
            source=source_enum
        ))
    return PipelineRunRequest(
        mode=mode,
        observations=observations,
    )
