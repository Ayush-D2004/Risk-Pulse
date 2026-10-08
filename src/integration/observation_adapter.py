from pydantic import BaseModel
from typing import Optional, List
from .runtime_models import PipelineRunRequest, RunMode, ObservationSource, ObservationInput
from src.ingestion.models import NewsDocument as GDELTNewsDocument


def adapt_gdelt_to_run_request(docs: List[GDELTNewsDocument]) -> PipelineRunRequest:
    observations = []
    for doc in docs:
        # Map GDELT NewsDocument fields to ObservationInput
        # Use body if available, otherwise title as text
        text = doc.body if doc.body else doc.title
        
        observations.append(ObservationInput(
            text=text,
            headline=doc.title,
            url=doc.url,
            entity=None,  # GDELT doesn't provide target_entity directly in the base model
            source=ObservationSource.GDELT,
            timestamp=doc.published_at,
            author=doc.publisher or doc.domain
        ))
        
    return PipelineRunRequest(
        mode=RunMode.LIVE_GDELT,
        observations=observations,
    )
