#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic Synthetic Portfolio Generator
============================================
Produces a fixed, reproducible wholesale banking book for stress testing.

Design decisions:
-----------------
1. **Deterministic**: No randomness.  Every call returns the identical portfolio.
2. **Overlap with Risk Engine entities**: Several obligors match entities already
   used in the RiskSignal / event pipeline (Boeing, Amazon, Tesla, Apple, etc.)
   to enable end-to-end signal → exposure → stress flow.
3. **Concentration**: Energy sector is deliberately concentrated, and one obligor
   (PetroGlobal Synthetic Corp) has a deliberately outsized position.
4. **Diversity**: Multiple sectors, geographies, credit qualities, asset types.
5. **Exact reconciliation**: All EADs are Decimal and sum exactly.
6. **Clearly synthetic**: Every obligor name and value is fictional or labelled.

The generator returns a Portfolio with a fixed as_of_date of 2024-06-30.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List

from src.portfolio.models import (
    AssetType,
    CreditRating,
    Exposure,
    Portfolio,
    PortfolioSummary,
)


# ---------------------------------------------------------------------------
# Synthetic obligor definitions
# ---------------------------------------------------------------------------
# Each entry: (obligor, ticker, aliases, sector, geography)
# Aliases MUST include the forms used in RiskSignal.entity for deterministic
# matching.  The ticker itself is also used as a matching key.

_OBLIGORS = [
    # ---- Technology (moderate concentration) ----
    ("Apple Inc. [Synthetic]", "AAPL", ["Apple", "Apple Inc.", "the iPhone maker"],
     "Technology", "US"),
    ("Microsoft Corp [Synthetic]", "MSFT", ["Microsoft", "Microsoft Corporation", "the software giant"],
     "Technology", "US"),
    ("Tesla Inc [Synthetic]", "TSLA", ["Tesla"],
     "Technology", "US"),
    ("Samsung Electronics [Synthetic]", "005930.KS", ["Samsung"],
     "Technology", "APAC"),

    # ---- Energy (DELIBERATELY CONCENTRATED) ----
    ("PetroGlobal [Synthetic]", "PTGL", ["PetroGlobal"],
     "Energy", "US"),
    ("Rosneft Oil Company [Synthetic]", "ROSN.ME", ["Rosneft", "Russian oil giant", "Rosneft Oil Company"],
     "Energy", "EMEA"),
    ("SaudiChem [Synthetic] Industries", "SCHM", ["SaudiChem"],
     "Energy", "MENA"),
    ("ShellEnergy [Synthetic] PLC", "SHLE", ["ShellEnergy"],
     "Energy", "EU"),

    # ---- Financials ----
    ("GlobalBank [Synthetic]", "GBKS", ["GlobalBank"],
     "Financials", "EU"),
    ("AsiaCredit [Synthetic] Ltd", "ACRD", ["AsiaCredit"],
     "Financials", "APAC"),

    # ---- Industrials ----
    ("Boeing Co [Synthetic]", "BA", ["Boeing", "Boeing Co"],
     "Industrials", "US"),

    # ---- Consumer ----
    ("Amazon.com Inc [Synthetic]", "AMZN", ["Amazon", "Amazon.com"],
     "Consumer", "US"),
    ("RetailCo [Synthetic] SA", "RTCO", ["RetailCo"],
     "Consumer", "LATAM"),

    # ---- Healthcare ----
    ("MedDevice [Synthetic] GmbH", "MDVS", ["MedDevice"],
     "Healthcare", "EU"),

    # ---- Sovereign / Quasi-sovereign (for macro/geopolitical events) ----
    ("Germany Sovereign [Synthetic]", None, ["Germany"],
     "Sovereign", "EMEA"),
]


# ---------------------------------------------------------------------------
# Exposure definitions
# ---------------------------------------------------------------------------
# Each tuple:
#   (obligor_index, asset_type, ead, rating, pd, lgd, maturity, duration, currency)
# obligor_index refers to _OBLIGORS list.

_EXPOSURES: list = [
    # ---- Apple — loan + bond ----
    (0, AssetType.CORPORATE_LOAN,   "50000000",  CreditRating.AA,  "0.0005", "0.35", "2027-06-30", None,   "USD"),
    (0, AssetType.CORPORATE_BOND,   "30000000",  CreditRating.AA,  "0.0005", "0.40", "2029-12-15", "4.2",  "USD"),

    # ---- Microsoft — loan ----
    (1, AssetType.CORPORATE_LOAN,   "40000000",  CreditRating.AAA, "0.0002", "0.30", "2026-09-30", None,   "USD"),

    # ---- Tesla — bond + equity ----
    (2, AssetType.CORPORATE_BOND,   "25000000",  CreditRating.BBB, "0.0120", "0.45", "2028-03-15", "3.5",  "USD"),
    (2, AssetType.EQUITY,           "10000000",  CreditRating.NR,  "0.0000", "1.00", "2099-12-31", None,   "USD"),

    # ---- Samsung — bond ----
    (3, AssetType.CORPORATE_BOND,   "20000000",  CreditRating.A,   "0.0030", "0.40", "2028-06-30", "3.8",  "KRW"),

    # ---- PetroGlobal (CONCENTRATED OBLIGOR) — loan + revolver + bond ----
    (4, AssetType.CORPORATE_LOAN,   "120000000", CreditRating.BB,  "0.0200", "0.55", "2026-12-31", None,   "USD"),
    (4, AssetType.REVOLVING_CREDIT, "80000000",  CreditRating.BB,  "0.0200", "0.55", "2025-12-31", None,   "USD"),
    (4, AssetType.CORPORATE_BOND,   "60000000",  CreditRating.BB,  "0.0200", "0.50", "2029-06-30", "4.5",  "USD"),

    # ---- Rosneft — loan ----
    (5, AssetType.CORPORATE_LOAN,   "35000000",  CreditRating.B,   "0.0350", "0.60", "2026-06-30", None,   "USD"),

    # ---- SaudiChem — bond ----
    (6, AssetType.CORPORATE_BOND,   "45000000",  CreditRating.BBB, "0.0100", "0.45", "2030-03-31", "5.2",  "USD"),

    # ---- ShellEnergy — loan + revolver ----
    (7, AssetType.CORPORATE_LOAN,   "55000000",  CreditRating.A,   "0.0025", "0.40", "2027-09-30", None,   "EUR"),
    (7, AssetType.REVOLVING_CREDIT, "25000000",  CreditRating.A,   "0.0025", "0.40", "2025-09-30", None,   "EUR"),

    # ---- GlobalBank — loan ----
    (8, AssetType.CORPORATE_LOAN,   "30000000",  CreditRating.A,   "0.0020", "0.45", "2027-03-31", None,   "EUR"),

    # ---- AsiaCredit — bond ----
    (9, AssetType.CORPORATE_BOND,   "15000000",  CreditRating.BBB, "0.0080", "0.50", "2028-12-31", "4.0",  "USD"),

    # ---- Boeing — loan + bond ----
    (10, AssetType.CORPORATE_LOAN,  "45000000",  CreditRating.BBB, "0.0090", "0.45", "2027-12-31", None,   "USD"),
    (10, AssetType.CORPORATE_BOND,  "20000000",  CreditRating.BBB, "0.0090", "0.50", "2030-06-30", "5.5",  "USD"),

    # ---- Amazon — loan + equity ----
    (11, AssetType.CORPORATE_LOAN,  "60000000",  CreditRating.AA,  "0.0004", "0.30", "2028-06-30", None,   "USD"),
    (11, AssetType.EQUITY,          "15000000",  CreditRating.NR,  "0.0000", "1.00", "2099-12-31", None,   "USD"),

    # ---- RetailCo — revolver ----
    (12, AssetType.REVOLVING_CREDIT,"18000000",  CreditRating.B,   "0.0300", "0.60", "2025-12-31", None,   "BRL"),

    # ---- MedDevice — bond ----
    (13, AssetType.CORPORATE_BOND,  "22000000",  CreditRating.A,   "0.0015", "0.35", "2029-03-31", "4.3",  "EUR"),

    # ---- CountryX Sovereign — bond ----
    (14, AssetType.CORPORATE_BOND,  "40000000",  CreditRating.CCC, "0.0800", "0.65", "2028-09-30", "3.9",  "USD"),
]


def _build_exposures() -> List[Exposure]:
    """Construct Exposure objects from the deterministic definitions."""
    exposures: List[Exposure] = []
    for idx, (obl_idx, asset_type, ead, rating, pd, lgd, mat, dur, ccy) in enumerate(_EXPOSURES):
        obligor_name, ticker, aliases, sector, geo = _OBLIGORS[obl_idx]
        exp = Exposure(
            exposure_id=f"EXP-{idx + 1:04d}",
            obligor=obligor_name,
            ticker=ticker,
            entity_aliases=aliases,
            sector=sector,
            geography=geo,
            asset_type=asset_type.value if isinstance(asset_type, AssetType) else asset_type,
            ead=Decimal(ead),
            currency=ccy,
            rating=rating.value if isinstance(rating, CreditRating) else rating,
            probability_of_default=Decimal(pd),
            loss_given_default=Decimal(lgd),
            maturity=date.fromisoformat(mat),
            duration=Decimal(dur) if dur is not None else None,
            is_synthetic=True,
        )
        exposures.append(exp)
    return exposures


def generate_synthetic_portfolio(as_of: date | None = None) -> Portfolio:
    """
    Generate the deterministic synthetic wholesale banking book.

    Args:
        as_of: Optional snapshot date.  Defaults to 2024-06-30.

    Returns:
        Portfolio containing all synthetic exposures.
    """
    snapshot = as_of or date(2024, 6, 30)
    exposures = _build_exposures()
    return Portfolio(
        portfolio_id="SYNTH-PORTFOLIO-001",
        name="Synthetic Wholesale Banking Book",
        as_of_date=snapshot,
        exposures=exposures,
        is_synthetic=True,
    )


# ---------------------------------------------------------------------------
# Aggregation / summary helper
# ---------------------------------------------------------------------------

def summarize_portfolio(portfolio: Portfolio) -> PortfolioSummary:
    """
    Compute aggregated portfolio statistics with concentration flags.

    Concentration flags are raised when:
        - A single sector exceeds 30% of total EAD
        - A single obligor exceeds 15% of total EAD
    """
    total = portfolio.total_ead
    by_sector: Dict[str, Decimal] = {}
    by_geography: Dict[str, Decimal] = {}
    by_asset_type: Dict[str, Decimal] = {}
    by_rating: Dict[str, Decimal] = {}
    by_obligor: Dict[str, Decimal] = {}

    for exp in portfolio.exposures:
        by_sector[exp.sector] = by_sector.get(exp.sector, Decimal("0")) + exp.ead
        by_geography[exp.geography] = by_geography.get(exp.geography, Decimal("0")) + exp.ead
        by_asset_type[exp.asset_type] = by_asset_type.get(exp.asset_type, Decimal("0")) + exp.ead
        by_rating[exp.rating] = by_rating.get(exp.rating, Decimal("0")) + exp.ead
        by_obligor[exp.obligor] = by_obligor.get(exp.obligor, Decimal("0")) + exp.ead

    # Top obligors by EAD
    sorted_obligors = sorted(by_obligor.items(), key=lambda x: x[1], reverse=True)
    top_obligors = [
        {"obligor": name, "ead": ead, "pct": round(float(ead / total * 100), 2) if total > 0 else 0}
        for name, ead in sorted_obligors[:10]
    ]

    # Concentration flags
    flags: List[str] = []
    if total > 0:
        for sector, ead in by_sector.items():
            pct = float(ead / total * 100)
            if pct > 30:
                flags.append(f"SECTOR CONCENTRATION: {sector} = {pct:.1f}% of total EAD")
        for name, ead in by_obligor.items():
            pct = float(ead / total * 100)
            if pct > 15:
                flags.append(f"OBLIGOR CONCENTRATION: {name} = {pct:.1f}% of total EAD")

    return PortfolioSummary(
        total_ead=total,
        exposure_count=portfolio.exposure_count,
        by_sector=by_sector,
        by_geography=by_geography,
        by_asset_type=by_asset_type,
        by_rating=by_rating,
        top_obligors=top_obligors,
        concentration_flags=flags,
    )
