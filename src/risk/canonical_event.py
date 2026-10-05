from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class CanonicalEvent(BaseModel):
    # Identity
    event_id: str
    cluster_id: str
    canonical_entity: str
    entity_status: str
    event_type: str
    timestamp: datetime  # event date

    # Risk
    sentiment_score: float
    event_confidence: float
    materiality: str
    impact_score: float
    impact_tier: str
    novelty: float

    # Source / Evidence
    observation_count: int
    source_types: List[str]
    representative_source_credibility: float
    representative_text: str
    representative_url: Optional[str]
    
    # Traceability
    source_row_ids: List[str]
    source_tweet_hashes: List[str]
    credit_guard_reason: Optional[str] = None
