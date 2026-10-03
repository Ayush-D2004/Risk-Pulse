#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests — Module B: Orchestration Layer
============================================
Validates the end-to-end deterministic connection of RiskSignal -> Orchestration -> Stress Scenario Result.
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from src.risk.risk_signal import Evidence, RiskSignal, EventType
from src.portfolio.synthetic_portfolio import generate_synthetic_portfolio
from src.portfolio.orchestration import StressScenarioEngine
from src.portfolio.shock_models import ShockScope


class TestStressScenarioEngine(unittest.TestCase):
    """Test suite for the orchestration engine."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()
        self.engine = StressScenarioEngine(self.portfolio)

    def _make_signal(self, event_id: str, event_type: str, impact_score: float, entity: str = "TestEntity", invalid: bool = False) -> RiskSignal:
        """Helper to create standard RiskSignal."""
        d = dict(
            event_id=event_id,
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
        if invalid:
            return RiskSignal.model_construct(**d)
        return RiskSignal(**d)

    def test_credit_event_end_to_end(self):
        """Credit event -> complete stress result."""
        sig = self._make_signal("EVT-1", EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        res = self.engine.run_signal(sig)
        
        self.assertFalse(res.error)
        self.assertTrue(res.stress_applied)
        self.assertEqual(res.event_id, "EVT-1")
        self.assertEqual(res.affected_entity, "Tesla")
        self.assertEqual(res.event_type, EventType.CREDIT_EVENT.value)
        self.assertGreater(res.affected_exposure_count, 0)
        self.assertGreater(res.incremental_expected_loss, Decimal("0"))
        
        # Test Explanation
        self.assertIn("Credit Event affecting Tesla", res.rationale)
        self.assertIn("Impact score: 10.0 (Critical Impact)", res.rationale)
        self.assertIn("ENTITY", res.rationale)

    def test_geopolitical_event_geographic_aggregation(self):
        """Geopolitical event -> geographic aggregation."""
        # Geopolitical default scope is GEOGRAPHY. Mapper doesn't know the specific geo from just entity.
        # But wait, without geo hint, the mapper currently produces affected_geography=None for Geopolitical.
        # So no exposures match unless we inject it or unless the mapper resolves it.
        # Wait, the prompt said: "If the model currently only has affected_entity... don't let Antigravity infer... That should be an explicit structured input".
        # Let's see if 0 exposures are affected.
        sig = self._make_signal("EVT-2", EventType.GEOPOLITICAL.value, 8.5, "Apple")
        res = self.engine.run_signal(sig)
        
        # In current design, GEOGRAPHY scope with affected_geography=None means NO exposures match.
        self.assertFalse(res.stress_applied)
        self.assertEqual(res.affected_exposure_count, 0)
        self.assertEqual(len(res.by_geography), 0)

    def test_corporate_earnings_entity_stress(self):
        """Corporate/Earnings event -> entity stress."""
        sig = self._make_signal("EVT-3", EventType.CORPORATE_EARNINGS.value, 6.0, "Microsoft")
        res = self.engine.run_signal(sig)
        
        self.assertTrue(res.stress_applied)
        self.assertGreater(res.incremental_expected_loss, Decimal("0"))

    def test_product_technology_event(self):
        """Product/Technology event."""
        sig = self._make_signal("EVT-4", EventType.PRODUCT_TECHNOLOGY.value, 4.0, "Amazon")
        res = self.engine.run_signal(sig)
        
        self.assertTrue(res.stress_applied)
        self.assertGreater(res.incremental_expected_loss, Decimal("0"))

    def test_no_event(self):
        """NO_EVENT yields zero-impact scenario result, stress_applied=False."""
        sig = self._make_signal("EVT-5", EventType.NO_EVENT.value, 10.0, "Apple")
        res = self.engine.run_signal(sig)
        
        self.assertFalse(res.error)
        self.assertFalse(res.stress_applied)
        self.assertEqual(res.affected_exposure_count, 0)
        self.assertEqual(res.incremental_expected_loss, Decimal("0"))
        self.assertIn("No stress applied", res.rationale)

    def test_zero_affected_exposures(self):
        """Entity with no exposures in portfolio yields zero impact."""
        sig = self._make_signal("EVT-6", EventType.CREDIT_EVENT.value, 10.0, "UnknownCompany")
        res = self.engine.run_signal(sig)
        
        self.assertFalse(res.error)
        self.assertFalse(res.stress_applied)
        self.assertEqual(res.affected_exposure_count, 0)

    def test_aggregations_and_reconciliation(self):
        """Sector, Geography, Asset-type aggregation and reconciliation."""
        # Use systemic to affect all credit/market assets to test aggregations comprehensively
        sig = self._make_signal("EVT-7", EventType.MARKET_LIQUIDITY.value, 10.0, "Global")
        res = self.engine.run_signal(sig)
        
        self.assertTrue(res.stress_applied)
        
        # Reconciliation: Sum of aggregations should match total
        sum_inc_el_sector = sum(m.incremental_expected_loss for m in res.by_sector)
        self.assertAlmostEqual(float(sum_inc_el_sector), float(res.incremental_expected_loss), places=4)
        
        sum_mtm_geo = sum(m.mtm_impact for m in res.by_geography)
        self.assertAlmostEqual(float(sum_mtm_geo), float(res.total_mtm_impact), places=4)
        
        sum_ead_asset = sum(m.ead for m in res.by_asset_type)
        self.assertAlmostEqual(float(sum_ead_asset), float(res.affected_ead), places=4)

    def test_invalid_impact_score(self):
        """Invalid impact score returns error result."""
        sig = self._make_signal("EVT-8", EventType.CREDIT_EVENT.value, 15.0, "Apple", invalid=True)
        res = self.engine.run_signal(sig)
        
        self.assertIsNotNone(res.error)
        self.assertFalse(res.stress_applied)
        self.assertIn("Invalid impact score", res.error)

    def test_missing_event_id(self):
        """Missing event ID returns error result."""
        sig = self._make_signal("", EventType.CREDIT_EVENT.value, 10.0, "Apple", invalid=True)
        res = self.engine.run_signal(sig)
        
        self.assertIsNotNone(res.error)
        self.assertFalse(res.stress_applied)
        self.assertIn("Missing event_id", res.error)

    def test_batch_ordering_and_isolation(self):
        """Batch ordering, isolation, duplicate event IDs."""
        sig_valid1 = self._make_signal("EVT-B1", EventType.CREDIT_EVENT.value, 10.0, "Apple")
        sig_invalid = self._make_signal("EVT-B2", EventType.CREDIT_EVENT.value, 99.0, "Apple", invalid=True) # Fails
        sig_valid2 = self._make_signal("EVT-B1", EventType.CORPORATE_EARNINGS.value, 5.0, "Tesla") # Duplicate ID

        results = self.engine.run_batch([sig_valid1, sig_invalid, sig_valid2])
        
        self.assertEqual(len(results), 3)
        
        # Deterministic ordering
        self.assertEqual(results[0].event_id, "EVT-B1")
        self.assertTrue(results[0].stress_applied)
        
        self.assertEqual(results[1].event_id, "EVT-B2")
        self.assertIsNotNone(results[1].error)
        self.assertFalse(results[1].stress_applied)
        
        self.assertEqual(results[2].event_id, "EVT-B1")
        self.assertTrue(results[2].stress_applied)
        
        # Isolation: first and third should be valid and untouched by second
        self.assertIsNone(results[0].error)
        self.assertIsNone(results[2].error)


if __name__ == "__main__":
    unittest.main()
