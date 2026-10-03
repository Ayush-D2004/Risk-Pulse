#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestration Models
====================
Data models for the orchestration layer that connects RiskSignal to Portfolio Stress.

Provides:
- Aggregation breakdown (by sector, geography, asset type)
- Complete StressScenarioResult (combining RiskSignal info, ShockScenario, and StressedPortfolio)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field
from src.portfolio.shock_models import ShockScenario
from src.portfolio.stress_models import StressedExposure


class AggregationMetrics(BaseModel):
    """Aggregated stress metrics for a specific dimension (e.g., sector, geography)."""
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )
    dimension_value: str = Field(..., description="The value of the dimension (e.g., 'Energy')")
    exposure_count: int = Field(..., description="Number of affected exposures in this slice")
    ead: Decimal = Field(..., description="Total affected EAD in this slice")
    ead_pct_of_portfolio: float = Field(..., description="Percentage of total portfolio EAD")
    incremental_expected_loss: Decimal = Field(..., description="Incremental EL in this slice")
    mtm_impact: Decimal = Field(..., description="MTM impact in this slice")


class StressScenarioResult(BaseModel):
    """
    Immutable structured result of end-to-end stress orchestration.
    Contains the originating signal context, the applied shock, and the stressed portfolio metrics.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    # --- Originating Signal ---
    event_id: str = Field(..., description="Originating RiskSignal event_id")
    affected_entity: str = Field(..., description="Primary affected entity")
    event_type: str = Field(..., description="Event classification")
    impact_score: float = Field(..., description="Impact score [1.0, 10.0]")
    impact_tier: str = Field(..., description="Impact tier string")

    # --- Status ---
    stress_applied: bool = Field(..., description="Whether non-zero stress was applied")

    # --- Applied Shock ---
    shock_scenario: Optional[ShockScenario] = Field(None, description="The deterministic shock applied")

    # --- Portfolio Metrics ---
    affected_exposure_count: int = Field(..., description="Number of exposures affected")
    affected_ead: Decimal = Field(..., description="Total EAD affected")
    affected_ead_pct: float = Field(..., description="Percentage of portfolio EAD affected")
    
    base_expected_loss: Decimal = Field(..., description="Total base EL of portfolio")
    stressed_expected_loss: Decimal = Field(..., description="Total stressed EL of portfolio")
    incremental_expected_loss: Decimal = Field(..., description="Total incremental EL")
    total_mtm_impact: Decimal = Field(..., description="Total mark-to-market impact")

    # --- Aggregations ---
    by_sector: List[AggregationMetrics] = Field(default_factory=list, description="Affected metrics by sector")
    by_geography: List[AggregationMetrics] = Field(default_factory=list, description="Affected metrics by geography")
    by_asset_type: List[AggregationMetrics] = Field(default_factory=list, description="Affected metrics by asset type")

    # --- Explanations ---
    rationale: str = Field(..., description="Deterministic human-readable explanation")
    
    # --- Exposure Level Results ---
    stressed_exposures: List[StressedExposure] = Field(default_factory=list, description="Individual exposure results")
    
    # --- Error Handling ---
    error: Optional[str] = Field(None, description="Validation error message if the signal was unstressable")

