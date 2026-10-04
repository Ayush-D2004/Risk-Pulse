# -*- coding: utf-8 -*-
"""
Dashboard read-model / API contract
===================================
Read-only application layer that exposes Module B results as
JSON-serializable Pydantic DTOs for a future React dashboard.

Does not modify Risk Engine, ImpactScorer, ShockMapper, StressEngine,
StressScenarioEngine, ScenarioComparisonEngine, or portfolio definitions.
Does not recalculate EL, PD, LGD, MTM, affected EAD, or attribution %.
"""

from src.dashboard.models import (
    DASHBOARD_SCHEMA_VERSION,
    AttributionDifferences,
    AttributionDeltaRow,
    AttributionRow,
    ComparisonDeltas,
    DashboardEnvelope,
    EventStressOverviewData,
    EventStressOverviewResponse,
    ExposureAttributionRow,
    PortfolioOverviewData,
    PortfolioOverviewResponse,
    RiskAttributionData,
    RiskAttributionResponse,
    ScenarioComparisonData,
    ScenarioComparisonResponse,
)
from src.dashboard.service import DashboardReadService
from src.dashboard.serialization import to_json, to_jsonable
from src.dashboard.demo import (
    DEMO_GENERATED_AT,
    EVENT_GEOPOLITICAL,
    EVENT_NO_EVENT,
    EVENT_TESLA_CREDIT_8,
    EVENT_TESLA_CREDIT_10,
    build_demo_catalog,
    demo_signals,
)

__all__ = [
    "DASHBOARD_SCHEMA_VERSION",
    "AttributionDifferences",
    "AttributionDeltaRow",
    "AttributionRow",
    "ComparisonDeltas",
    "DashboardEnvelope",
    "DashboardReadService",
    "EventStressOverviewData",
    "EventStressOverviewResponse",
    "ExposureAttributionRow",
    "PortfolioOverviewData",
    "PortfolioOverviewResponse",
    "RiskAttributionData",
    "RiskAttributionResponse",
    "ScenarioComparisonData",
    "ScenarioComparisonResponse",
    "to_json",
    "to_jsonable",
    "DEMO_GENERATED_AT",
    "EVENT_GEOPOLITICAL",
    "EVENT_NO_EVENT",
    "EVENT_TESLA_CREDIT_8",
    "EVENT_TESLA_CREDIT_10",
    "build_demo_catalog",
    "demo_signals",
]
