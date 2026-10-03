#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stress Models
=============
Data models for the outputs of the Portfolio Stress Engine.

Provides:
- StressedExposure: Represents a single portfolio exposure post-shock.
- StressedPortfolio: Aggregated portfolio-level metrics post-shock.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class StressedExposure(BaseModel):
    """
    Deterministic post-shock metrics for a single exposure.
    Contains both the base values and the stressed values.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    exposure_id: str = Field(..., description="Original exposure ID")
    obligor: str = Field(..., description="Original obligor name")
    asset_type: str = Field(..., description="Asset class")
    sector: str = Field(..., description="Sector")
    geography: str = Field(..., description="Geography")
    ead: Decimal = Field(..., description="Exposure at Default")

    is_affected: bool = Field(..., description="Whether this exposure was in-scope for the shock")

    # --- Credit Metrics ---
    base_pd: Decimal = Field(..., description="Base Probability of Default [0, 1]")
    stressed_pd: Decimal = Field(..., description="Post-shock Probability of Default [0, 1]")
    base_lgd: Decimal = Field(..., description="Base Loss Given Default [0, 1]")
    stressed_lgd: Decimal = Field(..., description="Post-shock Loss Given Default [0, 1]")

    base_expected_loss: Decimal = Field(..., description="Base Expected Loss (EAD * PD * LGD)")
    stressed_expected_loss: Decimal = Field(..., description="Post-shock Expected Loss")
    incremental_expected_loss: Decimal = Field(..., description="Stressed EL - Base EL")

    # --- Market Metrics ---
    base_market_value: Decimal = Field(..., description="Base market value (uses EAD)")
    stressed_market_value: Decimal = Field(..., description="Post-shock market value")
    mtm_impact: Decimal = Field(..., description="Stressed MV - Base MV")

    # --- Audit / Provenance ---
    event_id: Optional[str] = Field(None, description="Event ID that caused the stress")
    scenario_id: Optional[str] = Field(None, description="ShockScenario Rule ID")


class StressedPortfolio(BaseModel):
    """
    Aggregated portfolio-level stress metrics.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    portfolio_id: str = Field(..., description="Original portfolio ID")
    
    # --- Exposure summaries ---
    total_exposures: int = Field(..., description="Total number of exposures")
    affected_exposure_count: int = Field(..., description="Number of affected exposures")
    
    total_ead: Decimal = Field(..., description="Total Portfolio EAD")
    affected_ead: Decimal = Field(..., description="Total EAD of affected exposures")
    affected_ead_pct: float = Field(..., description="Percentage of portfolio EAD affected [0.0, 1.0]")

    # --- Aggregated Loss ---
    base_expected_loss: Decimal = Field(..., description="Sum of base expected loss")
    stressed_expected_loss: Decimal = Field(..., description="Sum of stressed expected loss")
    incremental_expected_loss: Decimal = Field(..., description="Sum of incremental EL")

    # --- Aggregated Market Impact ---
    total_base_market_value: Decimal = Field(..., description="Sum of base market values for MTM assets")
    total_stressed_market_value: Decimal = Field(..., description="Sum of stressed market values for MTM assets")
    total_mtm_impact: Decimal = Field(..., description="Sum of MTM impact (negative means loss)")

    # --- Individual Results ---
    stressed_exposures: List[StressedExposure] = Field(..., description="Detailed exposure-level results")

    # --- Audit ---
    event_id: Optional[str] = Field(None, description="Originating Event ID")
    scenario_id: Optional[str] = Field(None, description="Applied ShockScenario Rule ID")
