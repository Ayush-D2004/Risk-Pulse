#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests — Module B: Event -> Shock Mapping
==============================================
Validates the ShockMapper's deterministic conversion of a RiskSignal into a ShockScenario.

Tests include:
    - Base shock translation (High-impact Credit Event, Geopolitical, Earnings, Regulatory, NO_EVENT, etc.)
    - Scope mapping correctly derived from EventType.
    - Severity factor scaling & monotonicity with respect to impact score.
    - Boundaries (impact=1, impact=10).
    - Invalid impact score rejections.
    - Output determinism for repeated calls.
"""

import unittest
from datetime import datetime, timezone

from src.risk.risk_signal import Evidence, RiskSignal, EventType
from src.portfolio.shock_models import ShockScope, MAX_PD_DELTA, MAX_LGD_DELTA, MAX_BOND_SHOCK_NEG, MAX_EQUITY_SHOCK_NEG
from src.portfolio.shock_mapper import ShockMapper


class TestShockMapper(unittest.TestCase):
    """Test suite for ShockMapper."""

    def setUp(self):
        self.mapper = ShockMapper()

    def _make_signal(self, event_type: str, impact_score: float) -> RiskSignal:
        """Helper to create a standard test RiskSignal."""
        return RiskSignal(
            entity="TestEntity",
            source="test_source",
            sentiment_score=-0.5,
            event_type=event_type,
            event_confidence=0.9,
            materiality="MATERIAL_EVENT",
            impact_score=impact_score,
            evidence=Evidence(text="Test evidence"),
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def test_credit_event_high_impact(self):
        """Test Credit Event at impact=10 -> Maximum base shocks, ENTITY scope."""
        sig = self._make_signal(EventType.CREDIT_EVENT.value, impact_score=10.0)
        scenario = self.mapper.map(sig)
        
        self.assertEqual(scenario.event_type, EventType.CREDIT_EVENT.value)
        self.assertEqual(scenario.shock_scope, ShockScope.ENTITY.value)
        self.assertEqual(scenario.severity_factor, 1.0)
        
        # Base shocks from rule table for Credit Event:
        # pd=0.15, lgd=0.15, bond=-0.20, eq=-0.40
        self.assertAlmostEqual(scenario.pd_delta, 0.15)
        self.assertAlmostEqual(scenario.lgd_delta, 0.15)
        self.assertAlmostEqual(scenario.bond_price_shock, -0.20)
        self.assertAlmostEqual(scenario.equity_price_shock, -0.40)
        self.assertIsNone(scenario.affected_sector)
        self.assertIsNone(scenario.affected_geography)

    def test_geopolitical_event_high_impact(self):
        """Test Geopolitical Event -> GEOGRAPHY scope."""
        sig = self._make_signal(EventType.GEOPOLITICAL.value, impact_score=8.5)
        scenario = self.mapper.map(sig)
        
        self.assertEqual(scenario.event_type, EventType.GEOPOLITICAL.value)
        self.assertEqual(scenario.shock_scope, ShockScope.GEOGRAPHY.value)
        
        # At 8.5 impact, severity factor is (8.5 - 1) / 9 = 0.833333
        expected_severity = round(7.5 / 9.0, 6)
        self.assertAlmostEqual(scenario.severity_factor, expected_severity)
        
        # Geopolitical base: pd=0.05, lgd=0.05, bond=-0.10, eq=-0.15
        self.assertAlmostEqual(scenario.pd_delta, round(0.05 * expected_severity, 6))

    def test_earnings_event_moderate_impact(self):
        """Test Corporate / Earnings Event at impact=5.5 -> 0.5 severity factor."""
        sig = self._make_signal(EventType.CORPORATE_EARNINGS.value, impact_score=5.5)
        scenario = self.mapper.map(sig)
        
        self.assertEqual(scenario.shock_scope, ShockScope.ENTITY.value)
        self.assertAlmostEqual(scenario.severity_factor, 0.5)
        
        # Base: pd=0.03 -> scaled=0.015
        self.assertAlmostEqual(scenario.pd_delta, 0.015)

    def test_no_event(self):
        """Test NO_EVENT yields zero shocks and NONE scope, regardless of impact score."""
        sig = self._make_signal(EventType.NO_EVENT.value, impact_score=10.0)
        scenario = self.mapper.map(sig)
        
        self.assertEqual(scenario.shock_scope, ShockScope.NONE.value)
        self.assertEqual(scenario.pd_delta, 0.0)
        self.assertEqual(scenario.lgd_delta, 0.0)
        self.assertEqual(scenario.bond_price_shock, 0.0)
        self.assertEqual(scenario.equity_price_shock, 0.0)

    def test_monotonicity(self):
        """Higher impact score should yield greater or equal absolute shock magnitudes."""
        sig_low = self._make_signal(EventType.CREDIT_EVENT.value, impact_score=3.0)
        sig_med = self._make_signal(EventType.CREDIT_EVENT.value, impact_score=6.0)
        sig_high = self._make_signal(EventType.CREDIT_EVENT.value, impact_score=9.0)
        
        scen_low = self.mapper.map(sig_low)
        scen_med = self.mapper.map(sig_med)
        scen_high = self.mapper.map(sig_high)
        
        self.assertLess(scen_low.pd_delta, scen_med.pd_delta)
        self.assertLess(scen_med.pd_delta, scen_high.pd_delta)
        
        # Price shocks are negative, so their absolute magnitude increases (values become more negative)
        self.assertGreater(scen_low.equity_price_shock, scen_med.equity_price_shock)
        self.assertGreater(scen_med.equity_price_shock, scen_high.equity_price_shock)

    def test_impact_score_boundaries(self):
        """Test at impact=1.0 and 10.0 boundaries."""
        sig_min = self._make_signal(EventType.REGULATORY_LEGAL.value, impact_score=1.0)
        scen_min = self.mapper.map(sig_min)
        self.assertEqual(scen_min.severity_factor, 0.0)
        self.assertEqual(scen_min.pd_delta, 0.0)
        
        sig_max = self._make_signal(EventType.REGULATORY_LEGAL.value, impact_score=10.0)
        scen_max = self.mapper.map(sig_max)
        self.assertEqual(scen_max.severity_factor, 1.0)

    def test_invalid_impact_score_raises(self):
        """Impact scores outside [1.0, 10.0] should raise ValueError."""
        with self.assertRaises(ValueError):
            sig_low = self._make_signal(EventType.CREDIT_EVENT.value, impact_score=0.5)
            self.mapper.map(sig_low)
            
        with self.assertRaises(ValueError):
            sig_high = self._make_signal(EventType.CREDIT_EVENT.value, impact_score=11.0)
            self.mapper.map(sig_high)

    def test_determinism(self):
        """Repeated calls with the same RiskSignal should yield identical ShockScenarios."""
        sig = self._make_signal(EventType.PRODUCT_TECHNOLOGY.value, impact_score=7.3)
        scen1 = self.mapper.map(sig)
        scen2 = self.mapper.map(sig)
        
        self.assertEqual(scen1.to_dict(), scen2.to_dict())

    def test_missing_impact_score_defaults_to_one(self):
        """If RiskSignal.impact_score is None, mapper defaults to 1.0."""
        sig = self._make_signal(EventType.MACROECONOMIC.value, impact_score=1.0)
        sig.impact_score = None
        scen = self.mapper.map(sig)
        
        self.assertEqual(scen.severity_factor, 0.0)
        self.assertEqual(scen.pd_delta, 0.0)

    def test_unclear_event_type_fallback(self):
        """An unknown event type should fall back to OTHER_UNCLEAR rule."""
        sig = self._make_signal("Some Unknown Event Type", impact_score=10.0)
        scen = self.mapper.map(sig)
        
        self.assertEqual(scen.shock_scope, ShockScope.ENTITY.value)
        self.assertEqual(scen.rule_id, "RULE-OTHER-01")


if __name__ == "__main__":
    unittest.main()
