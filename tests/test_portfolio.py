#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests — Module B: Synthetic Portfolio & Exposure Model
============================================================
Validates:
    1. Deterministic portfolio generation
    2. Exact entity match (ticker, obligor, alias)
    3. Entity with multiple exposures
    4. Entity with no exposure (explicit zero-result)
    5. Sector aggregation
    6. Geography aggregation
    7. Total EAD reconciliation (sum == portfolio total, exact Decimal)
    8. Concentration flags
    9. Portfolio fixture determinism (two calls produce identical output)
"""

import unittest
from datetime import date
from decimal import Decimal

from src.portfolio.models import (
    AssetType,
    CreditRating,
    Exposure,
    ExposureMatch,
    Portfolio,
    PortfolioSummary,
)
from src.portfolio.synthetic_portfolio import (
    generate_synthetic_portfolio,
    summarize_portfolio,
)
from src.portfolio.exposure_model import ExposureModel


class TestDeterministicPortfolioGeneration(unittest.TestCase):
    """Verify portfolio is deterministic and internally consistent."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()

    def test_portfolio_is_deterministic(self):
        """Two independent calls must produce identical portfolios."""
        p1 = generate_synthetic_portfolio()
        p2 = generate_synthetic_portfolio()
        self.assertEqual(p1.portfolio_id, p2.portfolio_id)
        self.assertEqual(p1.total_ead, p2.total_ead)
        self.assertEqual(p1.exposure_count, p2.exposure_count)
        for e1, e2 in zip(p1.exposures, p2.exposures):
            self.assertEqual(e1.exposure_id, e2.exposure_id)
            self.assertEqual(e1.obligor, e2.obligor)
            self.assertEqual(e1.ead, e2.ead)

    def test_portfolio_not_empty(self):
        """Portfolio must contain a meaningful number of exposures."""
        self.assertGreaterEqual(self.portfolio.exposure_count, 15)

    def test_total_ead_exact_reconciliation(self):
        """sum(exposure EADs) must exactly equal portfolio.total_ead."""
        manual_sum = sum((e.ead for e in self.portfolio.exposures), Decimal("0"))
        self.assertEqual(manual_sum, self.portfolio.total_ead)

    def test_all_exposures_synthetic(self):
        """Every exposure must be marked synthetic."""
        for exp in self.portfolio.exposures:
            self.assertTrue(exp.is_synthetic, f"{exp.exposure_id} not marked synthetic")

    def test_portfolio_marked_synthetic(self):
        """Portfolio container must be marked synthetic."""
        self.assertTrue(self.portfolio.is_synthetic)

    def test_exposure_ids_unique(self):
        """All exposure IDs must be unique."""
        ids = [e.exposure_id for e in self.portfolio.exposures]
        self.assertEqual(len(ids), len(set(ids)))

    def test_custom_as_of_date(self):
        """Portfolio accepts a custom snapshot date."""
        custom = generate_synthetic_portfolio(as_of=date(2025, 1, 1))
        self.assertEqual(custom.as_of_date, date(2025, 1, 1))
        self.assertEqual(custom.total_ead, self.portfolio.total_ead)

    def test_multiple_sectors_present(self):
        """Portfolio must span multiple sectors for diversification testing."""
        sectors = {e.sector for e in self.portfolio.exposures}
        self.assertGreaterEqual(len(sectors), 5)

    def test_multiple_geographies_present(self):
        """Portfolio must span multiple geographies."""
        geos = {e.geography for e in self.portfolio.exposures}
        self.assertGreaterEqual(len(geos), 3)

    def test_multiple_asset_types_present(self):
        """Portfolio must include loans, bonds, revolvers, and equity."""
        types = {e.asset_type for e in self.portfolio.exposures}
        self.assertIn(AssetType.CORPORATE_LOAN.value, types)
        self.assertIn(AssetType.CORPORATE_BOND.value, types)
        self.assertIn(AssetType.REVOLVING_CREDIT.value, types)
        self.assertIn(AssetType.EQUITY.value, types)

    def test_multiple_credit_ratings_present(self):
        """Portfolio must include investment-grade and sub-investment-grade."""
        ratings = {e.rating for e in self.portfolio.exposures}
        ig = {CreditRating.AAA.value, CreditRating.AA.value, CreditRating.A.value, CreditRating.BBB.value}
        sig = {CreditRating.BB.value, CreditRating.B.value, CreditRating.CCC.value}
        self.assertTrue(ratings & ig, "No investment-grade exposures")
        self.assertTrue(ratings & sig, "No sub-investment-grade exposures")

    def test_bond_exposures_have_duration(self):
        """All bond exposures must have a duration value."""
        bonds = [e for e in self.portfolio.exposures if e.asset_type == AssetType.CORPORATE_BOND.value]
        self.assertGreater(len(bonds), 0)
        for bond in bonds:
            self.assertIsNotNone(bond.duration, f"{bond.exposure_id} bond missing duration")
            self.assertGreater(bond.duration, Decimal("0"))

    def test_non_bond_exposures_duration_none(self):
        """Non-bond, non-equity exposures should not have duration."""
        loans = [e for e in self.portfolio.exposures
                 if e.asset_type in (AssetType.CORPORATE_LOAN.value, AssetType.REVOLVING_CREDIT.value)]
        for loan in loans:
            self.assertIsNone(loan.duration, f"{loan.exposure_id} non-bond has duration")


class TestExactEntityMatch(unittest.TestCase):
    """Verify deterministic entity → exposure matching."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()
        self.model = ExposureModel(self.portfolio)

    def test_match_by_ticker(self):
        """Ticker 'AAPL' should match Apple exposures."""
        result = self.model.match_entity("AAPL")
        self.assertTrue(result.matched)
        self.assertGreaterEqual(result.match_count, 2)  # loan + bond
        for exp in result.exposures:
            self.assertIn("Apple", exp.obligor)

    def test_match_by_ticker_case_insensitive(self):
        """Ticker matching must be case-insensitive."""
        r1 = self.model.match_entity("aapl")
        r2 = self.model.match_entity("AAPL")
        r3 = self.model.match_entity("Aapl")
        self.assertEqual(r1.total_ead, r2.total_ead)
        self.assertEqual(r2.total_ead, r3.total_ead)
        self.assertTrue(r1.matched)

    def test_match_by_alias(self):
        """Alias 'Boeing' should match Boeing exposures."""
        result = self.model.match_entity("Boeing")
        self.assertTrue(result.matched)
        self.assertGreaterEqual(result.match_count, 2)  # loan + bond

    def test_match_by_alias_risk_signal_entities(self):
        """Entities used in existing RiskSignal tests must match portfolio exposures."""
        risk_signal_entities = ["Amazon", "Boeing", "Tesla", "Apple", "Rosneft", "CountryX"]
        for entity in risk_signal_entities:
            result = self.model.match_entity(entity)
            self.assertTrue(
                result.matched,
                f"RiskSignal entity '{entity}' has no portfolio exposure match",
            )
            self.assertGreater(
                result.total_ead, Decimal("0"),
                f"RiskSignal entity '{entity}' matched but EAD is zero",
            )


class TestEntityWithMultipleExposures(unittest.TestCase):
    """Verify that entities with multiple facilities return all of them."""

    def setUp(self):
        self.model = ExposureModel(generate_synthetic_portfolio())

    def test_petroglobal_has_three_exposures(self):
        """PetroGlobal (concentrated obligor) should have loan + revolver + bond."""
        result = self.model.match_entity("PetroGlobal")
        self.assertTrue(result.matched)
        self.assertEqual(result.match_count, 3)
        asset_types = {e.asset_type for e in result.exposures}
        self.assertIn(AssetType.CORPORATE_LOAN.value, asset_types)
        self.assertIn(AssetType.REVOLVING_CREDIT.value, asset_types)
        self.assertIn(AssetType.CORPORATE_BOND.value, asset_types)

    def test_tesla_has_bond_and_equity(self):
        """Tesla should have a bond and an equity position."""
        result = self.model.match_entity("Tesla")
        self.assertTrue(result.matched)
        self.assertEqual(result.match_count, 2)
        asset_types = {e.asset_type for e in result.exposures}
        self.assertIn(AssetType.CORPORATE_BOND.value, asset_types)
        self.assertIn(AssetType.EQUITY.value, asset_types)

    def test_apple_has_loan_and_bond(self):
        """Apple should have a loan and a bond."""
        result = self.model.match_entity("Apple")
        self.assertTrue(result.matched)
        self.assertEqual(result.match_count, 2)

    def test_no_duplicate_exposures(self):
        """Matching must not return duplicate exposure IDs."""
        # "Apple Inc." is both an alias and close to obligor — verify no dups
        result = self.model.match_entity("Apple Inc.")
        ids = [e.exposure_id for e in result.exposures]
        self.assertEqual(len(ids), len(set(ids)))


class TestEntityWithNoExposure(unittest.TestCase):
    """Verify explicit zero-exposure results for unmatched entities."""

    def setUp(self):
        self.model = ExposureModel(generate_synthetic_portfolio())

    def test_unknown_entity_returns_zero(self):
        """Entity not in portfolio must return matched=False, total_ead=0."""
        result = self.model.match_entity("UnknownCorp XYZ")
        self.assertFalse(result.matched)
        self.assertEqual(result.total_ead, Decimal("0"))
        self.assertEqual(result.match_count, 0)
        self.assertEqual(len(result.exposures), 0)

    def test_empty_entity_returns_zero(self):
        """Empty string query must return zero-exposure result."""
        result = self.model.match_entity("")
        self.assertFalse(result.matched)
        self.assertEqual(result.total_ead, Decimal("0"))

    def test_partial_name_does_not_fuzzy_match(self):
        """Partial name 'Appl' must NOT match Apple (no fuzzy matching)."""
        result = self.model.match_entity("Appl")
        self.assertFalse(result.matched)

    def test_close_but_wrong_name(self):
        """'Amazone' (typo) must NOT match Amazon."""
        result = self.model.match_entity("Amazone")
        self.assertFalse(result.matched)


class TestSectorAggregation(unittest.TestCase):
    """Verify sector-level aggregation."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()
        self.model = ExposureModel(self.portfolio)

    def test_energy_sector_exists(self):
        """Energy sector must have exposures."""
        energy = self.model.by_sector("Energy")
        self.assertGreater(len(energy), 0)

    def test_energy_is_concentrated(self):
        """Energy sector must exceed 30% of total EAD (deliberate concentration)."""
        energy_ead = self.model.sector_ead("Energy")
        total_ead = self.portfolio.total_ead
        pct = float(energy_ead / total_ead * 100)
        self.assertGreater(pct, 30, f"Energy concentration only {pct:.1f}%, expected >30%")

    def test_sector_ead_sums_to_total(self):
        """Sum of all sector EADs must exactly equal portfolio total."""
        sector_total = Decimal("0")
        for sector in self.model.all_sectors():
            sector_total += self.model.sector_ead(sector)
        self.assertEqual(sector_total, self.portfolio.total_ead)

    def test_sector_case_insensitive(self):
        """Sector lookup must be case-insensitive."""
        e1 = self.model.by_sector("energy")
        e2 = self.model.by_sector("Energy")
        e3 = self.model.by_sector("ENERGY")
        self.assertEqual(len(e1), len(e2))
        self.assertEqual(len(e2), len(e3))

    def test_nonexistent_sector_returns_empty(self):
        """Unknown sector returns empty list and zero EAD."""
        result = self.model.by_sector("Space Mining")
        self.assertEqual(len(result), 0)
        self.assertEqual(self.model.sector_ead("Space Mining"), Decimal("0"))


class TestGeographyAggregation(unittest.TestCase):
    """Verify geography-level aggregation."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()
        self.model = ExposureModel(self.portfolio)

    def test_geography_ead_sums_to_total(self):
        """Sum of all geography EADs must exactly equal portfolio total."""
        geo_total = Decimal("0")
        for geo in self.model.all_geographies():
            geo_total += self.model.geography_ead(geo)
        self.assertEqual(geo_total, self.portfolio.total_ead)

    def test_us_geography_exists(self):
        """US geography must have exposures."""
        us = self.model.by_geography("US")
        self.assertGreater(len(us), 0)

    def test_multiple_geographies(self):
        """At least 3 distinct geographies must be present."""
        geos = self.model.all_geographies()
        self.assertGreaterEqual(len(geos), 3)


class TestTotalEADReconciliation(unittest.TestCase):
    """Strict EAD reconciliation — the core audit constraint."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()

    def test_sum_equals_total_exactly(self):
        """sum(asset EAD) == portfolio total EAD, exactly in Decimal."""
        computed = sum((e.ead for e in self.portfolio.exposures), Decimal("0"))
        self.assertEqual(computed, self.portfolio.total_ead)
        # Also verify it's a positive, non-trivial amount
        self.assertGreater(computed, Decimal("100000000"))

    def test_every_ead_is_positive(self):
        """All EADs must be strictly positive."""
        for exp in self.portfolio.exposures:
            self.assertGreater(exp.ead, Decimal("0"), f"{exp.exposure_id} has non-positive EAD")

    def test_ead_is_decimal_not_float(self):
        """EAD values must be Decimal, not float, to guarantee exact arithmetic."""
        for exp in self.portfolio.exposures:
            self.assertIsInstance(exp.ead, Decimal, f"{exp.exposure_id} EAD is {type(exp.ead)}")


class TestPortfolioSummary(unittest.TestCase):
    """Verify the summarize_portfolio helper."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()
        self.summary = summarize_portfolio(self.portfolio)

    def test_summary_total_matches(self):
        """Summary total EAD must match portfolio total."""
        self.assertEqual(self.summary.total_ead, self.portfolio.total_ead)

    def test_summary_count_matches(self):
        """Summary exposure count must match portfolio count."""
        self.assertEqual(self.summary.exposure_count, self.portfolio.exposure_count)

    def test_sector_sum_reconciles(self):
        """Sum of by_sector EADs must equal total."""
        sector_sum = sum(self.summary.by_sector.values(), Decimal("0"))
        self.assertEqual(sector_sum, self.summary.total_ead)

    def test_geography_sum_reconciles(self):
        """Sum of by_geography EADs must equal total."""
        geo_sum = sum(self.summary.by_geography.values(), Decimal("0"))
        self.assertEqual(geo_sum, self.summary.total_ead)

    def test_asset_type_sum_reconciles(self):
        """Sum of by_asset_type EADs must equal total."""
        type_sum = sum(self.summary.by_asset_type.values(), Decimal("0"))
        self.assertEqual(type_sum, self.summary.total_ead)

    def test_rating_sum_reconciles(self):
        """Sum of by_rating EADs must equal total."""
        rating_sum = sum(self.summary.by_rating.values(), Decimal("0"))
        self.assertEqual(rating_sum, self.summary.total_ead)

    def test_concentration_flags_present(self):
        """At least one concentration flag must be raised (Energy sector + PetroGlobal)."""
        self.assertGreaterEqual(len(self.summary.concentration_flags), 1)
        # Check for both sector and obligor concentration
        flag_text = " ".join(self.summary.concentration_flags)
        self.assertIn("SECTOR_CONCENTRATION", flag_text)
        self.assertIn("OBLIGOR_CONCENTRATION", flag_text)

    def test_top_obligors_ordered(self):
        """Top obligors must be ordered by EAD descending."""
        eads = [o["ead"] for o in self.summary.top_obligors]
        for i in range(len(eads) - 1):
            self.assertGreaterEqual(eads[i], eads[i + 1])


class TestExposureModelProperties(unittest.TestCase):
    """Verify ExposureModel convenience properties."""

    def setUp(self):
        self.model = ExposureModel(generate_synthetic_portfolio())

    def test_all_sectors_non_empty(self):
        self.assertGreater(len(self.model.all_sectors()), 0)

    def test_all_geographies_non_empty(self):
        self.assertGreater(len(self.model.all_geographies()), 0)

    def test_all_obligors_non_empty(self):
        self.assertGreater(len(self.model.all_obligors()), 0)

    def test_portfolio_property(self):
        """Model should expose underlying portfolio."""
        self.assertIsInstance(self.model.portfolio, Portfolio)
        self.assertEqual(self.model.portfolio.portfolio_id, "SYNTH-PORTFOLIO-001")


if __name__ == "__main__":
    unittest.main()
