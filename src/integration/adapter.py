#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Canonical Event Adapter
=======================
Converts a real canonical event from the pipeline output into the RiskSignal domain model.
"""

from typing import Any, Dict
import math
from datetime import datetime
from src.risk.risk_signal import RiskSignal, Evidence

class CanonicalEventAdapter:
    """
    Adapter to convert a raw canonical event record (e.g. from canonical_events.csv)
    into a structured RiskSignal.
    """
    
    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> RiskSignal:
        """
        Converts a canonical event row (dictionary) into a RiskSignal.
        
        Raises:
            ValueError: If the event is missing critical fields or if the entity is unresolved.
        """
        event_id = row.get("event_id")
        if not event_id or (isinstance(event_id, float) and math.isnan(event_id)):
            raise ValueError("Missing canonical event ID")

        entity = row.get("canonical_entity")
        if not entity or (isinstance(entity, float) and math.isnan(entity)):
            raise ValueError("Missing entity")

        entity_status = row.get("entity_status")
        if entity_status in ("unresolved_source", "unresolved_entity"):
            raise ValueError(f"Cannot adapt unresolved entity status: {entity_status}")
            
        event_type = row.get("event_type")
        if not event_type or (isinstance(event_type, float) and math.isnan(event_type)):
            raise ValueError("Unsupported or missing event type")

        impact_score = row.get("impact_score")
        if impact_score is None or (isinstance(impact_score, float) and math.isnan(impact_score)) or not (1.0 <= impact_score <= 10.0):
            raise ValueError(f"Invalid impact score: {impact_score}")

        sentiment_score = row.get("sentiment_score")
        if sentiment_score is None or (isinstance(sentiment_score, float) and math.isnan(sentiment_score)) or not (-1.0 <= sentiment_score <= 1.0):
            raise ValueError(f"Invalid sentiment score: {sentiment_score}")
            
        # Parse source types to string if it's a list string (e.g., "['news']")
        source_types = row.get("source_types", "historical_pipeline")
        if isinstance(source_types, str) and source_types.startswith("["):
            import ast
            try:
                parsed = ast.literal_eval(source_types)
                if parsed:
                    source_types = str(parsed[0])
                else:
                    source_types = "other"
            except:
                source_types = "other"

        # Construct Evidence
        evidence_text = row.get("representative_text", "No text provided")
        if isinstance(evidence_text, float) and math.isnan(evidence_text):
            evidence_text = "No text provided"
            
        url = row.get("representative_url")
        if isinstance(url, float) and math.isnan(url):
            url = None

        evidence = Evidence(
            text=evidence_text,
            url=url,
            raw_metadata={"row_data": row}
        )

        # Construct MarketContext if fields are present
        market_context_kwargs = {}
        for mc_field in ["abnormal_return", "volume_ratio", "volatility", "index_movement", "sector_movement"]:
            val = row.get(mc_field)
            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                market_context_kwargs[mc_field] = float(val)
                
        market_context = market_context_kwargs if market_context_kwargs else None

        return RiskSignal(
            event_id=event_id,
            timestamp=row.get("timestamp"),
            entity=entity,
            source=source_types,
            source_credibility=float(row.get("representative_source_credibility", 1.0)),
            sentiment_score=float(sentiment_score),
            event_type=event_type,
            event_confidence=float(row.get("event_confidence", 1.0)),
            materiality=row.get("materiality", "MATERIAL_EVENT"),
            novelty=float(row.get("novelty", 1.0)),
            market_context=market_context,
            impact_score=float(impact_score),
            evidence=evidence
        )
