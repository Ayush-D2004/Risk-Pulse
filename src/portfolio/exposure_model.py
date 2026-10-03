#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exposure Model — Entity → Exposure Matching
=============================================
Maps RiskSignal entities to portfolio exposures using deterministic matching.

Matching strategy (strict, no fuzzy):
1. Exact ticker match (case-insensitive)
2. Exact obligor name match (case-insensitive, stripped)
3. Exact alias match (case-insensitive, stripped)

If an entity has no exposure, an explicit ExposureMatch with
matched=False, total_ead=0, and empty exposures is returned.
No exposures are ever fabricated.

Designed for later extension with:
    - Sector-wide shock propagation
    - Geography-wide shock propagation
    - Fuzzy / embedding-based matching (future)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Set

from src.portfolio.models import (
    Exposure,
    ExposureMatch,
    Portfolio,
)


class ExposureModel:
    """
    Deterministic entity → exposure matcher for the wholesale banking book.

    Usage:
        model = ExposureModel(portfolio)
        match = model.match_entity("Boeing")   # returns ExposureMatch
        sector_exp = model.by_sector("Energy") # returns list of Exposure
    """

    def __init__(self, portfolio: Portfolio) -> None:
        self._portfolio = portfolio
        self._exposures = list(portfolio.exposures)

        # Pre-build deterministic lookup indices (all keys lowered + stripped)
        self._by_ticker: Dict[str, List[Exposure]] = {}
        self._by_obligor: Dict[str, List[Exposure]] = {}
        self._by_alias: Dict[str, List[Exposure]] = {}
        self._by_sector: Dict[str, List[Exposure]] = {}
        self._by_geography: Dict[str, List[Exposure]] = {}

        for exp in self._exposures:
            # Ticker index
            if exp.ticker:
                key = exp.ticker.strip().lower()
                self._by_ticker.setdefault(key, []).append(exp)

            # Obligor name index
            obl_key = exp.obligor.strip().lower()
            self._by_obligor.setdefault(obl_key, []).append(exp)

            # Alias index
            for alias in exp.entity_aliases:
                alias_key = alias.strip().lower()
                self._by_alias.setdefault(alias_key, []).append(exp)

            # Sector index
            sec_key = exp.sector.strip().lower()
            self._by_sector.setdefault(sec_key, []).append(exp)

            # Geography index
            geo_key = exp.geography.strip().lower()
            self._by_geography.setdefault(geo_key, []).append(exp)

    # ------------------------------------------------------------------
    # Entity matching
    # ------------------------------------------------------------------

    def match_entity(self, entity: str) -> ExposureMatch:
        """
        Match a RiskSignal entity string to portfolio exposures.

        Matching priority:
            1. Ticker (exact, case-insensitive)
            2. Obligor name (exact, case-insensitive)
            3. Alias (exact, case-insensitive)

        Returns:
            ExposureMatch with matched=True/False and total_ead.
            If no match, returns explicit zero-exposure result.
        """
        query = entity.strip().lower()
        matched_exposures: List[Exposure] = []
        seen_ids: Set[str] = set()

        # Priority 1: Ticker
        for exp in self._by_ticker.get(query, []):
            if exp.exposure_id not in seen_ids:
                matched_exposures.append(exp)
                seen_ids.add(exp.exposure_id)

        # Priority 2: Obligor name
        for exp in self._by_obligor.get(query, []):
            if exp.exposure_id not in seen_ids:
                matched_exposures.append(exp)
                seen_ids.add(exp.exposure_id)

        # Priority 3: Alias
        for exp in self._by_alias.get(query, []):
            if exp.exposure_id not in seen_ids:
                matched_exposures.append(exp)
                seen_ids.add(exp.exposure_id)

        total_ead = sum((e.ead for e in matched_exposures), Decimal("0"))

        return ExposureMatch(
            entity_query=entity,
            matched=len(matched_exposures) > 0,
            exposures=matched_exposures,
            total_ead=total_ead,
            match_count=len(matched_exposures),
        )

    # ------------------------------------------------------------------
    # Aggregation queries
    # ------------------------------------------------------------------

    def by_sector(self, sector: str) -> List[Exposure]:
        """Return all exposures in a given sector (case-insensitive)."""
        return list(self._by_sector.get(sector.strip().lower(), []))

    def by_geography(self, geography: str) -> List[Exposure]:
        """Return all exposures in a given geography (case-insensitive)."""
        return list(self._by_geography.get(geography.strip().lower(), []))

    def sector_ead(self, sector: str) -> Decimal:
        """Total EAD for a sector."""
        return sum((e.ead for e in self.by_sector(sector)), Decimal("0"))

    def geography_ead(self, geography: str) -> Decimal:
        """Total EAD for a geography."""
        return sum((e.ead for e in self.by_geography(geography)), Decimal("0"))

    def all_sectors(self) -> List[str]:
        """Distinct sectors in the portfolio."""
        return sorted({e.sector for e in self._exposures})

    def all_geographies(self) -> List[str]:
        """Distinct geographies in the portfolio."""
        return sorted({e.geography for e in self._exposures})

    def all_obligors(self) -> List[str]:
        """Distinct obligor names in the portfolio."""
        return sorted({e.obligor for e in self._exposures})

    @property
    def portfolio(self) -> Portfolio:
        """Access the underlying portfolio."""
        return self._portfolio
