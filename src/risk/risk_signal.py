#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Canonical RiskSignal Schema
===========================
Defines the unified data contract for the Risk Signal Engine.
Every upstream pipeline (Twitter, GDELT, SEC filings, news feeds) and
downstream component (Impact Scorer, Risk Aggregator, Portfolio Engine)
produces or consumes this standardized model.

Design Principles:
------------------
1. Source-agnostic: Supports twitter, gdelt, official filings, news, etc.
2. Sentiment != Impact: sentiment_score measures NLP polarity [-1, 1],
   while impact_score measures financial significance [1, 10].
3. Confidence != Impact: event_confidence measures classifier certainty [0, 1],
   while impact_score measures financial magnitude.
4. Materiality != Impact: materiality provides operational filtering / relevance,
   not financial magnitude.
5. Novelty: Decoupled for event clustering/deduplication across time.
6. Market Context: Accommodates market variables (volatility, abnormal returns,
   volume spikes, sector/index shifts) without breaking the core schema.
7. Evidence: Preserves raw text and provenance explaining why the signal exists.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class EventType(str, Enum):
    """Canonical event taxonomy categories."""
    CREDIT_EVENT = "Credit Event"
    GEOPOLITICAL = "Geopolitical"
    MACROECONOMIC = "Macroeconomic"
    MERGER_ACQUISITION = "Merger & Acquisition"
    REGULATORY_LEGAL = "Regulatory / Legal"
    CORPORATE_EARNINGS = "Corporate / Earnings"
    PRODUCT_TECHNOLOGY = "Product / Technology"
    COMMODITY_SUPPLY_CHAIN = "Commodity / Supply Chain"
    MARKET_LIQUIDITY = "Market / Liquidity"
    OTHER_UNCLEAR = "Other / Unclear"
    NO_EVENT = "NO_EVENT"


class MaterialityLevel(str, Enum):
    """Standard event materiality tiers."""
    MATERIAL_EVENT = "MATERIAL_EVENT"
    NON_MATERIAL_FINANCIAL_CONTENT = "NON_MATERIAL_FINANCIAL_CONTENT"
    NO_EVENT = "NO_EVENT"


class SignalSource(str, Enum):
    """Common signal origins (source field is agnostic and also accepts arbitrary strings)."""
    TWITTER = "twitter"
    GDELT = "gdelt"
    SEC_FILING = "sec_filing"
    NEWS = "news"
    OFFICIAL = "official"
    INTERNAL = "internal"
    OTHER = "other"


class MarketContext(BaseModel):
    """
    Market microstructure and price context at the time of signal observation.
    Supports arbitrary extra metrics via extra='allow'.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    volatility: Optional[float] = Field(
        default=None,
        description="Volatility metric (e.g. 30d realized vol, implied vol, or z-score)",
    )
    abnormal_return: Optional[float] = Field(
        default=None,
        description="Cumulative abnormal return (CAR) or idiosyncratic return over the event window",
    )
    volume_ratio: Optional[float] = Field(
        default=None,
        description="Observed trading volume relative to trailing baseline (e.g. 20d average)",
    )
    sector_movement: Optional[float] = Field(
        default=None,
        description="Sector benchmark return / performance during the observation window",
    )
    index_movement: Optional[float] = Field(
        default=None,
        description="Broad market index return (e.g. S&P 500) during the observation window",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional market metrics (e.g., CDS spreads, bid-ask spreads, liquidity)",
    )


class Evidence(BaseModel):
    """
    Preserves raw source content and auditable trace for why the signal was identified.
    Supports arbitrary extra fields via extra='allow'.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    text: str = Field(
        ...,
        min_length=1,
        description="Primary textual evidence (e.g. tweet body, news snippet, filing passage)",
    )
    headline: Optional[str] = Field(
        default=None,
        description="Article title or filing headline, if available",
    )
    url: Optional[str] = Field(
        default=None,
        description="URL, permalink, or document locator",
    )
    author: Optional[str] = Field(
        default=None,
        description="Author, social handle, publisher, or filing filer",
    )
    matched_keywords: List[str] = Field(
        default_factory=list,
        description="Rule keywords, regex patterns, or triggers matched upstream",
    )
    raw_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw unstructured payload from the source platform",
    )


class RiskSignal(BaseModel):
    """
    Canonical Risk Signal object.

    Consolidated output of upstream NLP / event detection pipelines,
    and single source of truth for downstream impact scoring, risk modeling,
    and portfolio management.
    """
    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )

    event_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        description="Unique event signal identifier across sources",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the underlying event or signal generation",
    )
    entity: str = Field(
        ...,
        min_length=1,
        description="Target company, ticker, asset, or sovereign entity",
    )
    source: str = Field(
        ...,
        min_length=1,
        description="Origin source identifier (e.g. 'twitter', 'gdelt', 'sec_filing', 'official')",
    )
    source_credibility: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Credibility / reliability weight of the source [0.0, 1.0]",
    )
    sentiment_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="NLP sentiment polarity [-1.0 negative to +1.0 positive]. Distinct from impact.",
    )
    event_type: str = Field(
        ...,
        min_length=1,
        description="Canonical event taxonomy classification (e.g., 'Credit Event')",
    )
    event_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="NLP classifier confidence in the event type [0.0, 1.0]. Distinct from impact.",
    )
    materiality: str = Field(
        ...,
        min_length=1,
        description="Operational materiality status (e.g., 'MATERIAL_EVENT'). Not synonymous with impact.",
    )
    novelty: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Freshness score [0.0 = duplicate/stale, 1.0 = breaking/new]. Derived from clustering.",
    )
    market_context: Optional[MarketContext] = Field(
        default=None,
        description="Quantitative market indicators (volatility, abnormal return, volume, etc.)",
    )
    impact_score: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=10.0,
        description="Financial impact score [1.0 to 10.0] computed by Impact Scoring Engine",
    )
    impact_reason: Optional[str] = Field(
        default=None,
        description="Explainable breakdown and rationale for the assigned impact score",
    )
    evidence: Evidence = Field(
        ...,
        description="Source text snippet and audit trail explaining why signal exists",
    )

    # -----------------------------------------------------------------------
    # Field Validators
    # -----------------------------------------------------------------------

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        """Parse datetime from various string representations or return datetime."""
        if isinstance(v, datetime):
            return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        if isinstance(v, str):
            clean_str = v.strip()
            # Try ISO standard first
            try:
                dt = datetime.fromisoformat(clean_str.replace("Z", "+00:00"))
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
            # Try common tabular date formats (e.g. DD/MM/YYYY, YYYY-MM-DD)
            for fmt in (
                "%d/%m/%Y",
                "%Y-%m-%d",
                "%d-%m-%Y",
                "%m/%d/%Y",
                "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
            ):
                try:
                    dt = datetime.strptime(clean_str, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        raise ValueError(f"Unable to parse timestamp: {v!r}")

    @field_validator("evidence", mode="before")
    @classmethod
    def coerce_evidence(cls, v: Any) -> Evidence:
        """Coerce raw strings or dicts into an Evidence instance."""
        if isinstance(v, Evidence):
            return v
        if isinstance(v, str):
            return Evidence(text=v)
        if isinstance(v, dict):
            if "text" not in v:
                # Fallback to common alternative text keys
                text = v.get("tweet") or v.get("content") or v.get("body") or v.get("summary")
                if not text:
                    text = str(v)
                return Evidence(text=str(text), raw_metadata=v)
            return Evidence(**v)
        raise ValueError(f"Cannot coerce {type(v)} to Evidence: {v!r}")

    @field_validator("market_context", mode="before")
    @classmethod
    def coerce_market_context(cls, v: Any) -> Optional[MarketContext]:
        """Coerce dictionary into MarketContext instance."""
        if v is None:
            return None
        if isinstance(v, MarketContext):
            return v
        if isinstance(v, dict):
            return MarketContext(**v)
        raise ValueError(f"Cannot coerce {type(v)} to MarketContext: {v!r}")

    # -----------------------------------------------------------------------
    # Serialization & Deserialization Helpers
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert the model into a dictionary suitable for JSON serialization."""
        return self.model_dump(mode="json")

    def to_json(self, indent: Optional[int] = None) -> str:
        """Serialize the model to a JSON string."""
        return self.model_dump_json(indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RiskSignal:
        """Instantiate RiskSignal from a Python dictionary."""
        return cls.model_validate(data)

    @classmethod
    def from_json(cls, json_str: str) -> RiskSignal:
        """Instantiate RiskSignal from a JSON string."""
        return cls.model_validate_json(json_str)
