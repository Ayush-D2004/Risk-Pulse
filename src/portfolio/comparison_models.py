#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scenario Comparison & Risk Attribution Models
=============================================
Data models for comparing multiple StressScenarioResults and generating risk attribution.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from src.portfolio.orchestration_models import StressScenarioResult
from src.portfolio.stress_models import StressedExposure


class AttributionMetrics(BaseModel):
    """
    Risk attribution metrics for a specific dimension value (e.g., sector='Energy').
    Includes both absolute values and percentages of the scenario totals.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    dimension_value: str = Field(..., description="The value of the dimension")
    exposure_count: int = Field(..., description="Number of affected exposures")
    
    ead: Decimal = Field(..., description="Total affected EAD")
    ead_pct: float = Field(..., description="EAD as a percentage of scenario's affected EAD")
    
    incremental_expected_loss: Decimal = Field(..., description="Incremental EL")
    incremental_expected_loss_pct: float = Field(..., description="Inc EL as a percentage of scenario's total Inc EL")
    
    mtm_impact: Decimal = Field(..., description="Mark-to-market impact")
    mtm_impact_pct: float = Field(..., description="MTM impact as a percentage of scenario's total MTM impact")


class RiskAttribution(BaseModel):
    """
    Comprehensive risk attribution for a single scenario.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    event_id: str = Field(..., description="Originating event ID")
    
    by_sector: List[AttributionMetrics] = Field(..., description="Attribution by sector")
    by_geography: List[AttributionMetrics] = Field(..., description="Attribution by geography")
    by_asset_type: List[AttributionMetrics] = Field(..., description="Attribution by asset class")
    
    top_exposures_by_ead: List[StressedExposure] = Field(..., description="Largest affected exposures by EAD")
    top_exposures_by_el: List[StressedExposure] = Field(..., description="Largest affected exposures by Inc EL")
    top_exposures_by_mtm: List[StressedExposure] = Field(..., description="Largest affected exposures by absolute MTM")


class ScenarioComparisonDelta(BaseModel):
    """
    Represents the mathematical differences between two scenarios (A and B).
    Delta = B - A
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    delta_affected_ead: Decimal = Field(..., description="B.affected_ead - A.affected_ead")
    delta_incremental_expected_loss: Decimal = Field(..., description="B.incremental_el - A.incremental_el")
    delta_absolute_mtm: Decimal = Field(..., description="abs(B.mtm) - abs(A.mtm)")


class ScenarioComparisonPair(BaseModel):
    """
    A descriptive comparison between two specific scenarios.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    scenario_a_id: str = Field(..., description="Event ID of Scenario A")
    scenario_b_id: str = Field(..., description="Event ID of Scenario B")
    
    scenario_a: StressScenarioResult = Field(..., description="Scenario A Result")
    scenario_b: StressScenarioResult = Field(..., description="Scenario B Result")
    
    deltas: ScenarioComparisonDelta = Field(..., description="Mathematical differences (B - A)")


class BatchComparisonMatrix(BaseModel):
    """
    Matrix/table representation comparing multiple scenarios side-by-side.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    scenario_ids: List[str] = Field(..., description="Ordered list of scenario event IDs")
    scenarios: List[StressScenarioResult] = Field(..., description="Ordered list of scenario results")
    attributions: List[RiskAttribution] = Field(..., description="Ordered list of risk attributions")
