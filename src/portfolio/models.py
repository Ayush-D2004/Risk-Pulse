#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Portfolio Data Models
=====================
Pydantic models representing a simplified wholesale banking book.

Supports:
    - Corporate loans
    - Corporate bonds
    - Revolving credit facilities
    - Equity exposure bucket

Each exposure carries fields required for later stress testing:
    PD, LGD, EAD, duration (bonds), rating bucket, maturity, sector, geography.

All values are clearly synthetic.  No real customer data is used.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AssetType(str, Enum):
    """Supported wholesale asset classes."""
    CORPORATE_LOAN = "Corporate Loan"
    CORPORATE_BOND = "Corporate Bond"
    REVOLVING_CREDIT = "Revolving Credit Facility"
    EQUITY = "Equity"


class CreditRating(str, Enum):
    """Simplified S&P-style rating buckets for the synthetic portfolio."""
    AAA = "AAA"
    AA = "AA"
    A = "A"
    BBB = "BBB"
    BB = "BB"
    B = "B"
    CCC = "CCC"
    NR = "NR"  # Not Rated (equity positions)


# ---------------------------------------------------------------------------
# Exposure model
# ---------------------------------------------------------------------------

class Exposure(BaseModel):
    """
    Single credit / market exposure in the wholesale banking book.

    Designed to be stress-tested later by RiskSignal-derived shocks:
        - PD increase
        - LGD increase
        - Bond price / duration shock
        - Equity price shock
        - Sector-wide shock
    """
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )

    # Identity
    exposure_id: str = Field(
        default_factory=lambda: f"EXP-{uuid.uuid4().hex[:8].upper()}",
        description="Unique exposure identifier",
    )
    obligor: str = Field(
        ...,
        min_length=1,
        description="Obligor / company name (synthetic)",
    )
    ticker: Optional[str] = Field(
        default=None,
        description="Ticker or entity identifier where available",
    )
    entity_aliases: List[str] = Field(
        default_factory=list,
        description="Alternative names for deterministic matching",
    )

    # Classification
    sector: str = Field(
        ...,
        min_length=1,
        description="Industry sector (e.g. Technology, Energy, Financials)",
    )
    geography: str = Field(
        ...,
        min_length=1,
        description="Geographic region (e.g. US, EU, APAC, LATAM)",
    )
    asset_type: str = Field(
        ...,
        description="Asset class (Corporate Loan, Corporate Bond, etc.)",
    )

    # Financials — use Decimal for exact reconciliation
    ead: Decimal = Field(
        ...,
        gt=0,
        description="Exposure at Default in USD (synthetic)",
    )
    currency: str = Field(
        default="USD",
        description="Exposure currency",
    )

    # Credit quality
    rating: str = Field(
        ...,
        description="Credit rating bucket (AAA through CCC, or NR)",
    )
    probability_of_default: Decimal = Field(
        ...,
        ge=0,
        le=1,
        description="Annualised probability of default [0, 1]",
    )
    loss_given_default: Decimal = Field(
        ...,
        ge=0,
        le=1,
        description="Loss given default [0, 1]",
    )

    # Maturity
    maturity: date = Field(
        ...,
        description="Contractual maturity date",
    )

    # Bond-specific
    duration: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Modified duration in years (bonds only)",
    )

    # Marker
    is_synthetic: bool = Field(
        default=True,
        description="Always True — labels data as synthetic",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("ead", mode="before")
    @classmethod
    def coerce_ead(cls, v: Any) -> Decimal:
        """Coerce numeric inputs to Decimal."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @field_validator("probability_of_default", "loss_given_default", mode="before")
    @classmethod
    def coerce_decimal_rates(cls, v: Any) -> Decimal:
        """Coerce numeric inputs to Decimal."""
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @field_validator("duration", mode="before")
    @classmethod
    def coerce_duration(cls, v: Any) -> Optional[Decimal]:
        """Coerce numeric inputs to Decimal, allow None."""
        if v is None:
            return None
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


# ---------------------------------------------------------------------------
# Exposure match result
# ---------------------------------------------------------------------------

class ExposureMatch(BaseModel):
    """
    Result of matching a RiskSignal entity to portfolio exposures.

    If no exposure exists for the entity, exposures will be empty and
    total_ead will be exactly zero — never fabricated.
    """
    model_config = ConfigDict(extra="forbid")

    entity_query: str = Field(
        ...,
        description="The entity name / ticker queried",
    )
    matched: bool = Field(
        ...,
        description="True if at least one exposure was found",
    )
    exposures: List[Exposure] = Field(
        default_factory=list,
        description="All matching exposures",
    )
    total_ead: Decimal = Field(
        default=Decimal("0"),
        description="Sum of EAD across matched exposures",
    )
    match_count: int = Field(
        default=0,
        description="Number of matched exposures",
    )


# ---------------------------------------------------------------------------
# Portfolio container
# ---------------------------------------------------------------------------

class Portfolio(BaseModel):
    """
    Container for the entire synthetic wholesale banking book.
    Guarantees exact EAD reconciliation via Decimal arithmetic.
    """
    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(
        default="SYNTH-PORTFOLIO-001",
        description="Portfolio identifier",
    )
    name: str = Field(
        default="Synthetic Wholesale Banking Book",
        description="Human-readable portfolio name",
    )
    as_of_date: date = Field(
        ...,
        description="Portfolio snapshot date",
    )
    exposures: List[Exposure] = Field(
        default_factory=list,
        description="All exposure positions",
    )
    is_synthetic: bool = Field(
        default=True,
        description="Always True — labels portfolio as synthetic",
    )

    @property
    def total_ead(self) -> Decimal:
        """Exact sum of all exposure EADs."""
        return sum((e.ead for e in self.exposures), Decimal("0"))

    @property
    def exposure_count(self) -> int:
        """Number of positions."""
        return len(self.exposures)


# ---------------------------------------------------------------------------
# Portfolio summary (aggregation helper)
# ---------------------------------------------------------------------------

class PortfolioSummary(BaseModel):
    """Aggregated portfolio statistics."""
    model_config = ConfigDict(extra="forbid")

    total_ead: Decimal
    exposure_count: int
    by_sector: Dict[str, Decimal]
    by_geography: Dict[str, Decimal]
    by_asset_type: Dict[str, Decimal]
    by_rating: Dict[str, Decimal]
    top_obligors: List[Dict[str, Any]]
    concentration_flags: List[str] = Field(default_factory=list)
