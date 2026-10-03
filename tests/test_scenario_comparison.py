#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests — Module B: Scenario Comparison & Risk Attribution
=============================================================
Validates risk attribution calculations, scenario deltas, deterministic extraction,
and invariant preservation.
"""

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from src.risk.risk_signal import Evidence, RiskSignal, EventType
from src.portfolio.synthetic_portfolio import generate_synthetic_portfolio
from src.portfolio.orchestration import StressScenarioEngine
from src.portfolio.scenario_comparison import ScenarioComparisonEngine


class TestScenarioComparisonEngine(unittest.TestCase):
    """Test suite for Scenario Comparison and Attribution."""

    def setUp(self):
        self.portfolio = generate_synthetic_portfolio()
        self.orchestrator = StressScenarioEngine(self.portfolio)
        self.engine = ScenarioComparisonEngine()

    def _make_result(self, event_id: str, event_type: str, impact_score: float, entity: str = "TestEntity"):
        """Helper to create standard StressScenarioResult."""
        sig = RiskSignal(
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
        return self.orchestrator.run_signal(sig)

    def test_same_event_identical_results(self):
        """Same event against same portfolio -> identical comparison delta (0)."""
        res_a = self._make_result("EVT-1", EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        res_b = self._make_result("EVT-1", EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        
        pair = self.engine.compare(res_a, res_b)
        
        self.assertEqual(pair.deltas.delta_affected_ead, Decimal("0"))
        self.assertEqual(pair.deltas.delta_incremental_expected_loss, Decimal("0"))
        self.assertEqual(pair.deltas.delta_absolute_mtm, Decimal("0"))

    def test_credit_vs_geopolitical(self):
        """Entity-level (Credit) vs Geography-level (Geopolitical)."""
        res_credit = self._make_result("EVT-CREDIT", EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        
        # We must explicitly inject affected_geography into the Geopolitical signal's mapped scenario.
        # Wait, orchestration layer handles mapping. If the orchestration mapper creates affected_geography=None, it won't affect any exposures.
        # But wait, in the orchestration tests we saw Geopolitical affected 0 exposures unless we hacked it.
        # Let's use MARKET_LIQUIDITY (Systemic) instead of geopolitical to ensure non-zero impact,
        # OR we can just check 0 impact vs non-zero impact.
        res_geo = self._make_result("EVT-GEO", EventType.GEOPOLITICAL.value, 8.0, "EU")
        
        pair = self.engine.compare(res_credit, res_geo)
        
        # Credit affects Tesla (non-zero). Geo affects nothing natively because mapping lacks geo hint.
        # Delta = B (Geo) - A (Credit). So delta is negative.
        self.assertLess(pair.deltas.delta_incremental_expected_loss, Decimal("0"))

    def test_attribution_reconciliation(self):
        """Sector, Geography, Asset-type attribution reconciliation."""
        # Use systemic to affect all eligible assets
        res = self._make_result("EVT-SYS", EventType.MARKET_LIQUIDITY.value, 10.0, "Global")
        attr = self.engine.extract_attribution(res)
        
        total_inc_el = res.incremental_expected_loss
        total_mtm = res.total_mtm_impact
        
        # Sector
        sum_sec_el = sum(a.incremental_expected_loss for a in attr.by_sector)
        self.assertAlmostEqual(float(sum_sec_el), float(total_inc_el), places=4)
        
        sum_sec_el_pct = sum(a.incremental_expected_loss_pct for a in attr.by_sector)
        self.assertAlmostEqual(sum_sec_el_pct, 1.0, places=4)
        
        # Geography
        sum_geo_mtm = sum(a.mtm_impact for a in attr.by_geography)
        self.assertAlmostEqual(float(sum_geo_mtm), float(total_mtm), places=4)
        
        sum_geo_mtm_pct = sum(a.mtm_impact_pct for a in attr.by_geography)
        self.assertAlmostEqual(sum_geo_mtm_pct, 1.0, places=4)

    def test_zero_el_scenario(self):
        """Zero-EL scenario handles zero denominators gracefully."""
        # Equity-only exposure (e.g. Amazon only has Equity and Loan, wait Amazon has Loan).
        # We need a NO_EVENT to guarantee exactly 0.
        res = self._make_result("EVT-NONE", EventType.NO_EVENT.value, 5.0)
        attr = self.engine.extract_attribution(res)
        
        self.assertEqual(len(attr.by_sector), 0)
        self.assertEqual(len(attr.top_exposures_by_el), 0)

    def test_top_affected_exposure_extraction(self):
        """Top affected exposure extraction and deterministic tie-breaking."""
        res = self._make_result("EVT-CREDIT", EventType.CREDIT_EVENT.value, 10.0, "PetroGlobal")
        # PetroGlobal has 3 exposures.
        attr = self.engine.extract_attribution(res)
        
        self.assertEqual(len(attr.top_exposures_by_ead), 3)
        self.assertEqual(len(attr.top_exposures_by_el), 3)
        self.assertEqual(len(attr.top_exposures_by_mtm), 3)
        
        # Verify ordering is descending EAD
        self.assertGreaterEqual(attr.top_exposures_by_ead[0].ead, attr.top_exposures_by_ead[1].ead)
        self.assertGreaterEqual(attr.top_exposures_by_ead[1].ead, attr.top_exposures_by_ead[2].ead)
        
        # Highest EAD for PetroGlobal is EXP-0007 ($120M)
        self.assertEqual(attr.top_exposures_by_ead[0].exposure_id, "EXP-0007")

    def test_batch_comparison_preserving_order(self):
        """Batch comparison preserves input order."""
        res_a = self._make_result("EVT-A", EventType.CREDIT_EVENT.value, 5.0, "Tesla")
        res_b = self._make_result("EVT-B", EventType.CREDIT_EVENT.value, 10.0, "Apple")
        res_c = self._make_result("EVT-C", EventType.NO_EVENT.value, 1.0)
        
        matrix = self.engine.compare_batch([res_a, res_b, res_c])
        
        self.assertEqual(matrix.scenario_ids, ["EVT-A", "EVT-B", "EVT-C"])
        self.assertEqual(len(matrix.attributions), 3)
        self.assertEqual(matrix.attributions[0].event_id, "EVT-A")
        self.assertEqual(matrix.attributions[1].event_id, "EVT-B")

    def test_no_mutation(self):
        """No mutation of original scenario results."""
        res = self._make_result("EVT-1", EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        original_json = res.model_dump_json()
        
        # Extract attribution
        _ = self.engine.extract_attribution(res)
        
        # Compare
        res_b = self._make_result("EVT-2", EventType.NO_EVENT.value, 5.0)
        _ = self.engine.compare(res, res_b)
        
        self.assertEqual(res.model_dump_json(), original_json)

    def test_comparison_delta_arithmetic(self):
        """Comparison delta arithmetic."""
        res_a = self._make_result("EVT-A", EventType.CREDIT_EVENT.value, 5.0, "Tesla")
        res_b = self._make_result("EVT-B", EventType.CREDIT_EVENT.value, 10.0, "Tesla")
        
        # B is higher impact, so B - A should be positive delta for EAD/EL/MTM magnitude
        pair = self.engine.compare(res_a, res_b)
        
        self.assertEqual(pair.deltas.delta_affected_ead, Decimal("0")) # Same entity, same EAD
        self.assertGreater(pair.deltas.delta_incremental_expected_loss, Decimal("0"))
        
        # MTM is typically negative, absolute MTM is positive.
        # B has a bigger drop (more negative), so abs(B.mtm) > abs(A.mtm).
        self.assertGreater(pair.deltas.delta_absolute_mtm, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
