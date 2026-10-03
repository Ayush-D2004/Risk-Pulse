#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shock Scenario Data Models
===========================
Immutable/structured output of the Event → Shock Mapping layer.

A ShockScenario is produced by mapping a RiskSignal through the deterministic
rule table.  It does NOT modify the RiskSignal or portfolio exposures.  It is
a pure *parameter set* consumed by the downstream stress engine (Step 13).

Units
-----
- PD delta:        absolute probability points (e.g. 0.05 = +5 pp)
- LGD delta:       absolute points (e.g. 0.10 = +10 pp)
- Bond price shock: decimal return (e.g. -0.08 = −8% price move)
- Equity price shock: decimal return (e.g. -0.15 = −15% price move)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class ShockScope(str, Enum):
    """Determines the propagation breadth of a shock event."""
    ENTITY = "ENTITY"               # Single obligor / company
    SECTOR = "SECTOR"               # All exposures in the affected sector
    GEOGRAPHY = "GEOGRAPHY"         # All exposures in the affected geography
    BROAD_MARKET = "BROAD_MARKET"   # Macro / market-wide
    SYSTEMIC = "SYSTEMIC"           # Cross-asset, cross-sector (rare)
    NONE = "NONE"                   # No shock (NO_EVENT / sub-threshold)


class ApplicableAsset(str, Enum):
    """Flags which asset classes a shock component targets."""
    CORPORATE_LOAN = "Corporate Loan"
    CORPORATE_BOND = "Corporate Bond"
    REVOLVING_CREDIT = "Revolving Credit Facility"
    EQUITY = "Equity"


# ---------------------------------------------------------------------------
# Asset-class applicability map
# ---------------------------------------------------------------------------
# Defines which shock fields are relevant for each asset type.

ASSET_SHOCK_APPLICABILITY: Dict[str, Set[str]] = {
    "Corporate Loan":              {"pd_delta", "lgd_delta"},
    "Revolving Credit Facility":   {"pd_delta", "lgd_delta"},
    "Corporate Bond":              {"pd_delta", "lgd_delta", "bond_price_shock"},
    "Equity":                      {"equity_price_shock"},
}


# ---------------------------------------------------------------------------
# Maximum absolute bounds (safety clamps)
# ---------------------------------------------------------------------------

MAX_PD_DELTA: float = 0.20          # +20 pp maximum PD increase
MAX_LGD_DELTA: float = 0.20         # +20 pp maximum LGD increase
MAX_BOND_SHOCK_NEG: float = -0.30   # −30% bond price floor
MAX_BOND_SHOCK_POS: float = 0.10    # +10% bond price ceiling
MAX_EQUITY_SHOCK_NEG: float = -0.50 # −50% equity price floor
MAX_EQUITY_SHOCK_POS: float = 0.10  # +10% equity price ceiling


# ---------------------------------------------------------------------------
# ShockScenario — immutable output
# ---------------------------------------------------------------------------

class ShockScenario(BaseModel):
    """
    Immutable stress parameter set produced by the Event → Shock Mapper.

    This object carries *all* shock parameters for one event.  The downstream
    stress engine selects which fields to apply based on `applicable_assets`
    and the exposure's asset type.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,          # immutable after creation
        populate_by_name=True,
    )

    # --- Identity (traced back to the originating RiskSignal) ---
    event_id: str = Field(
        ...,
        description="Event ID from the originating RiskSignal",
    )
    event_type: str = Field(
        ...,
        description="Canonical event type classification",
    )
    impact_score: float = Field(
        ...,
        ge=1.0,
        le=10.0,
        description="Impact score [1.0, 10.0] from the ImpactScorer",
    )
    impact_tier: str = Field(
        ...,
        description="Qualitative impact tier (Critical, High, Moderate, Low, Minimal)",
    )
    affected_entity: str = Field(
        ...,
        description="Primary entity from the RiskSignal",
    )

    # --- Scope ---
    shock_scope: str = Field(
        ...,
        description="Propagation scope: ENTITY, SECTOR, GEOGRAPHY, BROAD_MARKET, SYSTEMIC, NONE",
    )
    affected_sector: Optional[str] = Field(
        default=None,
        description="Sector affected (when scope is SECTOR or broader)",
    )
    affected_geography: Optional[str] = Field(
        default=None,
        description="Geography affected (when scope is GEOGRAPHY or broader)",
    )

    # --- Quantitative shock parameters ---
    pd_delta: float = Field(
        ...,
        ge=0.0,
        le=MAX_PD_DELTA,
        description="Absolute PD increase in probability points [0, 0.20]",
    )
    lgd_delta: float = Field(
        ...,
        ge=0.0,
        le=MAX_LGD_DELTA,
        description="Absolute LGD increase in points [0, 0.20]",
    )
    bond_price_shock: float = Field(
        ...,
        ge=MAX_BOND_SHOCK_NEG,
        le=MAX_BOND_SHOCK_POS,
        description="Bond price change as decimal return [-0.30, +0.10]",
    )
    equity_price_shock: float = Field(
        ...,
        ge=MAX_EQUITY_SHOCK_NEG,
        le=MAX_EQUITY_SHOCK_POS,
        description="Equity price change as decimal return [-0.50, +0.10]",
    )

    # --- Severity factor (derived from impact score) ---
    severity_factor: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized severity: (impact_score - 1) / 9, monotonic [0, 1]",
    )

    # --- Applicability ---
    applicable_assets: List[str] = Field(
        ...,
        description="Asset types to which this shock scenario applies",
    )

    # --- Audit ---
    rule_id: str = Field(
        ...,
        description="Identifier of the deterministic rule that produced this scenario",
    )
    rationale: str = Field(
        ...,
        description="Human-readable explanation of the shock derivation",
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return self.model_dump(mode="json")
