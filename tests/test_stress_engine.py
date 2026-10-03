#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests — Module B: Portfolio Stress Engine
===============================================
Validates deterministic execution of stress shocks over the synthetic portfolio.
Checks all accounting invariants and required fixtures.
"""

import unittest
from copy import deepcopy
from decimal import Decimal
from datetime import datetime, timezone

from src.risk.risk_signal import Evidence, RiskSignal, EventType
from src.portfolio.synthetic_portfolio import generate_synthetic_portfolio
from src.portfolio.shock_mapper import ShockMapper
from src.portfolio.stress_engine import StressEngine
from src.portfolio.models import AssetType


class TestStressEngine(unittest.TestCase):
    """Test suite for the deterministic Portfolio Stress Engine."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()
        # Create a deep copy to verify the engine doesn't mutate the original portfolio
        self.original_portfolio_copy = deepcopy(self.portfolio)
        
        self.mapper = ShockMapper()
        self.engine = StressEngine(self.portfolio)

    def _make_scenario(
        self, event_type: str, impact_score: float, entity: str = "TestEntity",
        affected_sector: str = None, affected_geography: str = None
    ):
        """Helper to create a ShockScenario through the mapper."""
        sig = RiskSignal(
            entity=entity,
            source="test",
            sentiment_score=0.0,
            event_type=event_type,
            event_confidence=1.0,
            materiality="MATERIAL_EVENT",
            impact_score=impact_score,
            evidence=Evidence(text="Test"),
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        scenario = self.mapper.map(sig)
        
        # Inject sector/geography if needed since RiskSignal doesn't inherently contain it
        if affected_sector or affected_geography:
            # Reconstruct the frozen model with hints
            d = scenario.to_dict()
            if affected_sector:
                d["affected_sector"] = affected_sector
            if affected_geography:
                d["affected_geography"] = affected_geography
            from src.portfolio.shock_models import ShockScenario
            scenario = ShockScenario(**d)
            
        return scenario

    def _assert_invariants(self, stressed_portfolio):
        """Check all mathematical and accounting invariants for a given result."""
        # Incremental EL = Stressed EL - Base EL
        self.assertAlmostEqual(
            float(stressed_portfolio.incremental_expected_loss),
            float(stressed_portfolio.stressed_expected_loss - stressed_portfolio.base_expected_loss),
            places=4,
            msg="Portfolio incremental EL mismatch"
        )
        
        sum_incremental_el = sum(e.incremental_expected_loss for e in stressed_portfolio.stressed_exposures)
        self.assertAlmostEqual(
            float(stressed_portfolio.incremental_expected_loss),
            float(sum_incremental_el),
            places=4,
            msg="Aggregated incremental EL != sum of exposure incremental ELs"
        )
        
        sum_mtm_impact = sum(e.mtm_impact for e in stressed_portfolio.stressed_exposures)
        self.assertAlmostEqual(
            float(stressed_portfolio.total_mtm_impact),
            float(sum_mtm_impact),
            places=4,
            msg="Aggregated MTM != sum of exposure MTMs"
        )
        
        for exp in stressed_portfolio.stressed_exposures:
            # PD and LGD monotonicity and bounds
            self.assertGreaterEqual(exp.stressed_pd, exp.base_pd)
            self.assertGreaterEqual(exp.stressed_lgd, exp.base_lgd)
            self.assertLessEqual(exp.stressed_pd, Decimal("1.0"))
            self.assertLessEqual(exp.stressed_lgd, Decimal("1.0"))
            
            # Exposure level EL match
            self.assertAlmostEqual(
                float(exp.incremental_expected_loss),
                float(exp.stressed_expected_loss - exp.base_expected_loss),
                places=4,
                msg=f"Exposure incremental EL mismatch on {exp.exposure_id}"
            )
            
            if not exp.is_affected:
                self.assertEqual(exp.stressed_pd, exp.base_pd)
                self.assertEqual(exp.stressed_lgd, exp.base_lgd)
                self.assertEqual(exp.incremental_expected_loss, Decimal("0"))
                self.assertEqual(exp.mtm_impact, Decimal("0"))
                
    def test_invariants_and_immutability(self):
        """Original portfolio remains untouched after stress execution."""
        scenario = self._make_scenario(EventType.CREDIT_EVENT.value, 10.0, "Apple")
        _ = self.engine.run_stress(scenario)
        
        # Validate original portfolio identity
        self.assertEqual(self.portfolio.total_ead, self.original_portfolio_copy.total_ead)
        for orig, current in zip(self.original_portfolio_copy.exposures, self.portfolio.exposures):
            self.assertEqual(orig.probability_of_default, current.probability_of_default)
            self.assertEqual(orig.loss_given_default, current.loss_given_default)
            self.assertEqual(orig.ead, current.ead)

    def test_determinism(self):
        """Repeated executions must produce identical outputs."""
        scenario = self._make_scenario(EventType.CREDIT_EVENT.value, 10.0, "Apple")
        res1 = self.engine.run_stress(scenario)
        res2 = self.engine.run_stress(scenario)
        
        self.assertEqual(res1.model_dump_json(), res2.model_dump_json())

    def test_no_event(self):
        """NO_EVENT yields zero EL and zero MTM impact."""
        scenario = self._make_scenario(EventType.NO_EVENT.value, 10.0)
        res = self.engine.run_stress(scenario)
        
        self._assert_invariants(res)
        self.assertEqual(res.affected_exposure_count, 0)
        self.assertEqual(res.incremental_expected_loss, Decimal("0"))
        self.assertEqual(res.total_mtm_impact, Decimal("0"))

    def test_credit_event_one_entity(self):
        """High-impact Credit Event affecting one obligor (PetroGlobal)."""
        scenario = self._make_scenario(EventType.CREDIT_EVENT.value, 10.0, "PetroGlobal")
        res = self.engine.run_stress(scenario)
        
        self._assert_invariants(res)
        
        self.assertGreater(res.affected_exposure_count, 0)
        self.assertGreater(res.incremental_expected_loss, Decimal("0"))
        
        # PetroGlobal has a bond, so MTM impact should be negative
        self.assertLess(res.total_mtm_impact, Decimal("0"))

    def test_geopolitical_event_geography(self):
        """High-impact Geopolitical event affecting a geography."""
        scenario = self._make_scenario(
            EventType.GEOPOLITICAL.value, 10.0,
            affected_geography="EU"
        )
        res = self.engine.run_stress(scenario)
        self._assert_invariants(res)
        
        # Check EU exposures are affected
        eu_count = sum(1 for e in res.stressed_exposures if e.geography == "EU" and e.is_affected)
        self.assertGreater(eu_count, 0)
        
        # US exposures should NOT be affected
        us_affected = sum(1 for e in res.stressed_exposures if e.geography == "US" and e.is_affected)
        self.assertEqual(us_affected, 0)

    def test_moderate_corporate_earnings(self):
        """Moderate Corporate/Earnings event."""
        scenario = self._make_scenario(EventType.CORPORATE_EARNINGS.value, 5.5, "Tesla")
        res = self.engine.run_stress(scenario)
        self._assert_invariants(res)
        
        self.assertGreater(res.incremental_expected_loss, Decimal("0"))

    def test_product_technology(self):
        """Product/Technology event."""
        scenario = self._make_scenario(EventType.PRODUCT_TECHNOLOGY.value, 8.0, "Microsoft")
        res = self.engine.run_stress(scenario)
        self._assert_invariants(res)
        
        # Microsoft only has a corporate loan in our portfolio.
        # So we should see incremental EL but NO MTM impact (loans are not MTM assets here).
        self.assertGreater(res.incremental_expected_loss, Decimal("0"))
        self.assertEqual(res.total_mtm_impact, Decimal("0"))

    def test_regulatory_event(self):
        """Regulatory event."""
        scenario = self._make_scenario(EventType.REGULATORY_LEGAL.value, 9.0, "Amazon")
        res = self.engine.run_stress(scenario)
        self._assert_invariants(res)
        self.assertGreater(res.incremental_expected_loss, Decimal("0"))
        # Amazon has equity, which gets equity price shock -> negative MTM
        self.assertLess(res.total_mtm_impact, Decimal("0"))

    def test_pd_lgd_capping(self):
        """Verify PD/LGD do not exceed 1.0 even with large shocks on high base values."""
        # Find an exposure with high PD, e.g. CountryX Sovereign (PD=0.08)
        scenario = self._make_scenario(EventType.CREDIT_EVENT.value, 10.0, "CountryX")
        # Overwrite the scenario PD delta to be huge for testing the cap
        from src.portfolio.shock_models import ShockScenario
        d = scenario.model_dump()
        d["pd_delta"] = 0.99  # Massive delta
        scenario_hacked = ShockScenario.model_construct(**d)
        
        res = self.engine.run_stress(scenario_hacked)
        self._assert_invariants(res)
        
        for exp in res.stressed_exposures:
            if exp.is_affected:
                self.assertLessEqual(exp.stressed_pd, Decimal("1.0"))

    def test_irrelevant_asset_classes_do_not_receive_inappropriate_shocks(self):
        """Verify equity doesn't get PD shocks, loans don't get MTM shocks."""
        scenario = self._make_scenario(EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        res = self.engine.run_stress(scenario)
        
        for exp in res.stressed_exposures:
            if exp.is_affected and exp.asset_type == AssetType.EQUITY.value:
                # Equity should only get MTM impact, no incremental EL
                self.assertEqual(exp.incremental_expected_loss, Decimal("0"))
                self.assertLess(exp.mtm_impact, Decimal("0"))
            elif exp.is_affected and exp.asset_type == AssetType.CORPORATE_LOAN.value:
                # Loans should get incremental EL, no MTM impact
                self.assertGreater(exp.incremental_expected_loss, Decimal("0"))
                self.assertEqual(exp.mtm_impact, Decimal("0"))

    def test_bond_and_equity_mtm_shock(self):
        """Verify negative bond/equity shocks reduce market value."""
        # Tesla has both a bond and equity
        scenario = self._make_scenario(EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        res = self.engine.run_stress(scenario)
        
        for exp in res.stressed_exposures:
            if exp.is_affected:
                self.assertLess(exp.stressed_market_value, exp.base_market_value)
                self.assertLess(exp.mtm_impact, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
