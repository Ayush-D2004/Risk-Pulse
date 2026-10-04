#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard read models (API contract)
====================================
JSON-serializable, schema-stable DTOs for a future React dashboard.

These models are projections of already-computed Module B outputs.
They do not contain financial formulas. Decimal fields are copied
from StressScenarioResult / RiskAttribution / PortfolioSummary.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


DASHBOARD_SCHEMA_VERSION = "1.0.0"


class FrozenDto(BaseModel):
    """Base DTO: closed, immutable, JSON-friendly."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )


class DashboardEnvelope(FrozenDto):
    """Common envelope required on every dashboard response."""

    schema_version: str = Field(..., description="Stable contract version")
    generated_at: datetime = Field(
        ...,
        description="Response metadata timestamp; never used in financial calculations",
    )
    portfolio_id: str = Field(..., description="Portfolio identifier")
    event_id: Optional[str] = Field(
        default=None,
        description="Primary event / scenario identifier when a single result is shown",
    )
    scenario_a_id: Optional[str] = Field(
        default=None,
        description="Scenario A event_id for comparison views",
    )
    scenario_b_id: Optional[str] = Field(
        default=None,
        description="Scenario B event_id for comparison views",
    )


# ---------------------------------------------------------------------------
# Portfolio overview
# ---------------------------------------------------------------------------

class EadSlice(FrozenDto):
    """Named EAD bucket copied from PortfolioSummary aggregations."""

    name: str
    ead: Decimal


class ObligorConcentrationRow(FrozenDto):
    """Top-obligor row copied from PortfolioSummary.top_obligors."""

    obligor: str
    ead: Decimal
    pct: float


class PortfolioOverviewData(FrozenDto):
    total_ead: Decimal
    exposure_count: int
    obligor_count: int
    sector_distribution: List[EadSlice]
    geography_distribution: List[EadSlice]
    rating_distribution: List[EadSlice]
    top_obligors: List[ObligorConcentrationRow]
    concentration_indicators: List[str]


class PortfolioOverviewResponse(DashboardEnvelope):
    data: PortfolioOverviewData


# ---------------------------------------------------------------------------
# Event stress overview
# ---------------------------------------------------------------------------

class EventStressOverviewData(FrozenDto):
    event_id: str
    entity: str
    event_type: str
    sentiment: float
    impact_score: float
    impact_tier: str
    shock_scope: Optional[str] = None
    affected_ead: Decimal
    affected_ead_pct: float
    incremental_el: Decimal
    mtm_impact: Decimal
    deterministic_rationale: str
    stress_applied: bool


class EventStressOverviewResponse(DashboardEnvelope):
    data: EventStressOverviewData


# ---------------------------------------------------------------------------
# Risk attribution
# ---------------------------------------------------------------------------

class AttributionRow(FrozenDto):
    """
    Copied from AttributionMetrics (sector / geography / asset type).
    Percentages are those already computed by ScenarioComparisonEngine.
    """

    dimension_value: str
    exposure_count: int
    ead: Decimal
    ead_pct: float
    incremental_el: Decimal
    incremental_el_pct: float
    mtm_impact: Decimal
    mtm_contribution_pct: float


class ExposureAttributionRow(FrozenDto):
    """
    Copied exposure-level stress metrics.
    Percentages are omitted because ScenarioComparisonEngine does not
    compute attribution percentages at exposure grain — this layer
    must not invent them.
    """

    exposure_id: str
    obligor: str
    asset_type: str
    sector: str
    geography: str
    ead: Decimal
    incremental_el: Decimal
    mtm_impact: Decimal
    is_affected: bool


class RiskAttributionData(FrozenDto):
    event_id: str
    by_sector: List[AttributionRow]
    by_geography: List[AttributionRow]
    by_asset_type: List[AttributionRow]
    by_exposure: List[ExposureAttributionRow]


class RiskAttributionResponse(DashboardEnvelope):
    data: RiskAttributionData


# ---------------------------------------------------------------------------
# Scenario comparison
# ---------------------------------------------------------------------------

class ComparisonDeltas(FrozenDto):
    """Copied from ScenarioComparisonDelta (B − A). No qualitative labels."""

    affected_ead_difference: Decimal
    incremental_el_difference: Decimal
    absolute_mtm_difference: Decimal


class AttributionDeltaRow(FrozenDto):
    """
    Per-dimension difference of already-computed attribution metrics (B − A).
    Missing side is treated as zero copies, not as a newly calculated loss.
    """

    dimension_value: str
    ead_difference: Decimal
    incremental_el_difference: Decimal
    mtm_impact_difference: Decimal
    ead_pct_difference: float
    incremental_el_pct_difference: float
    mtm_contribution_pct_difference: float


class AttributionDifferences(FrozenDto):
    by_sector: List[AttributionDeltaRow]
    by_geography: List[AttributionDeltaRow]
    by_asset_type: List[AttributionDeltaRow]


class ScenarioComparisonData(FrozenDto):
    scenario_a: EventStressOverviewData
    scenario_b: EventStressOverviewData
    deltas: ComparisonDeltas
    attribution_differences: AttributionDifferences


class ScenarioComparisonResponse(DashboardEnvelope):
    data: ScenarioComparisonData
