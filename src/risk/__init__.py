# -*- coding: utf-8 -*-
"""
Risk Signal Engine
==================
Core data structures and scoring modules for evaluating financial risk signals.

Note: MarketEnrichedScorer lives in src.risk.market_enriched_scorer and is
imported directly to avoid circular import with src.market.market_context.
"""

from src.risk.impact_scorer import (
    DEFAULT_EVENT_SEVERITY,
    ImpactScoreResult,
    ImpactScorer,
)
from src.risk.risk_signal import (
    Evidence,
    EventType,
    MarketContext,
    MaterialityLevel,
    RiskSignal,
    SignalSource,
)

__all__ = [
    "RiskSignal",
    "MarketContext",
    "Evidence",
    "EventType",
    "MaterialityLevel",
    "SignalSource",
    "ImpactScorer",
    "ImpactScoreResult",
    "DEFAULT_EVENT_SEVERITY",
]
