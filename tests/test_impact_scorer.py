# -*- coding: utf-8 -*-
"""
Unit tests for Deterministic ImpactScorer v1.
"""

import unittest

from src.risk.impact_scorer import (
    DEFAULT_EVENT_SEVERITY,
    ImpactScoreResult,
    ImpactScorer,
)
from src.risk.risk_signal import (
    Evidence,
    EventType,
    MarketContext,
    MaterialityLevel,
    RiskSignal,
)


class TestImpactScorer(unittest.TestCase):
    """Test suite verifying impact scoring logic, materiality gating, and explainability."""

    def setUp(self):
        self.scorer = ImpactScorer()

    def test_user_benchmark_examples(self):
        """
        Verify the 5 benchmark cases from the design spec:
        1. Minor feature: Sentiment +0.8, Product -> Low (impact ~ 2.5 - 3.5)
        2. Misses earnings badly: Sentiment -0.7, Corporate/Earnings -> High (impact ~ 6.5 - 7.5)
        3. Sovereign default: Sentiment -0.9, Credit -> Very High (impact ~ 9.0 - 10.0)
        4. Major acquisition: Sentiment +0.2, M&A -> Potentially high (impact ~ 6.0 - 7.0)
        5. Central bank rate decision: Sentiment -0.1, Macro -> Potentially high (impact ~ 6.5 - 7.5)
        """
        # Case 1: Minor product feature
        sig_product = RiskSignal(
            entity="TechCorp",
            source="twitter",
            source_credibility=0.8,
            sentiment_score=0.8,
            event_type="Product / Technology",
            event_confidence=0.65,
            materiality="MATERIAL_EVENT",
            evidence="Company launches minor new widget feature.",
        )
        res_product = self.scorer.calculate(sig_product)
        self.assertLessEqual(res_product.impact_score, 4.5)
        self.assertGreaterEqual(res_product.impact_score, 2.0)
        self.assertEqual(res_product.impact_tier, "Low Impact")

        # Case 2: Misses earnings badly
        sig_earnings = RiskSignal(
            entity="RetailCo",
            source="news",
            source_credibility=1.0,
            sentiment_score=-0.7,
            event_type="Corporate / Earnings",
            event_confidence=0.90,
            materiality="MATERIAL_EVENT",
            evidence="RetailCo misses quarterly EPS by 40%, slashes forward guidance.",
        )
        res_earnings = self.scorer.calculate(sig_earnings)
        self.assertGreaterEqual(res_earnings.impact_score, 6.5)
        self.assertLessEqual(res_earnings.impact_score, 7.8)

        # Case 3: Sovereign default / extreme credit
        sig_credit = RiskSignal(
            entity="CountryX",
            source="official",
            source_credibility=1.0,
            sentiment_score=-0.9,
            event_type="Credit Event",
            event_confidence=0.95,
            materiality="MATERIAL_EVENT",
            evidence="CountryX enters sovereign debt default after missing payment grace period.",
        )
        res_credit = self.scorer.calculate(sig_credit)
        self.assertGreaterEqual(res_credit.impact_score, 9.0)
        self.assertEqual(res_credit.impact_tier, "Critical Impact")

        # Case 4: Major acquisition announced
        sig_ma = RiskSignal(
            entity="MegaCorp",
            source="news",
            source_credibility=1.0,
            sentiment_score=0.2,
            event_type="Merger & Acquisition",
            event_confidence=0.88,
            materiality="MATERIAL_EVENT",
            evidence="MegaCorp announces $25B definitive acquisition agreement.",
        )
        res_ma = self.scorer.calculate(sig_ma)
        self.assertGreaterEqual(res_ma.impact_score, 6.0)
        self.assertLessEqual(res_ma.impact_score, 7.2)

        # Case 5: Central bank rate decision
        sig_macro = RiskSignal(
            entity="CentralBank",
            source="official",
            source_credibility=1.0,
            sentiment_score=-0.1,
            event_type="Macroeconomic",
            event_confidence=0.92,
            materiality="MATERIAL_EVENT",
            evidence="Central Bank hikes benchmark interest rate by 50 basis points.",
        )
        res_macro = self.scorer.calculate(sig_macro)
        self.assertGreaterEqual(res_macro.impact_score, 6.5)
        self.assertLessEqual(res_macro.impact_score, 7.5)

    def test_materiality_gate_no_event(self):
        """NO_EVENT must strictly clamp impact to 1.0, even with catastrophic sentiment/event."""
        sig = RiskSignal(
            entity="AcmeCorp",
            source="twitter",
            source_credibility=1.0,
            sentiment_score=-1.0,
            event_type="Credit Event",
            event_confidence=0.99,
            materiality="NO_EVENT",
            evidence="I'm bankrupt because Acme coffee was terrible!",
        )
        res = self.scorer.calculate(sig)
        self.assertEqual(res.impact_score, 1.0)
        self.assertTrue(res.is_gated)
        self.assertIn("NO_EVENT", res.impact_reason)

    def test_materiality_gate_non_material_financial_content(self):
        """NON_MATERIAL_FINANCIAL_CONTENT must strictly clamp impact to [1.0, 2.0]."""
        sig = RiskSignal(
            entity="AcmeCorp",
            source="twitter",
            source_credibility=1.0,
            sentiment_score=-0.95,
            event_type="Credit Event",
            event_confidence=0.95,
            materiality="NON_MATERIAL_FINANCIAL_CONTENT",
            evidence="Personal loan default complaint mentioning company.",
        )
        res = self.scorer.calculate(sig)
        self.assertGreaterEqual(res.impact_score, 1.0)
        self.assertLessEqual(res.impact_score, 2.0)
        self.assertTrue(res.is_gated)
        self.assertIn("non-material", res.impact_reason.lower())

    def test_sentiment_is_not_main_driver(self):
        """
        Verify that a highly negative sentiment does not push an insignificant event high,
        and neutral sentiment does not crush a material macro/M&A event.
        """
        # Minor event with extreme negative sentiment (-0.95)
        sig_minor_neg = RiskSignal(
            entity="GadgetInc",
            source="twitter",
            source_credibility=0.5,
            sentiment_score=-0.95,
            event_type="Other / Unclear",
            event_confidence=0.40,
            materiality="MATERIAL_EVENT",
            evidence="Terrible app icon redesign update.",
        )
        res_minor = self.scorer.calculate(sig_minor_neg)
        # Should stay low (< 3.0) despite extreme negative sentiment
        self.assertLess(res_minor.impact_score, 3.0)

        # Macro event with near-zero sentiment (0.0)
        sig_macro_neutral = RiskSignal(
            entity="Fed",
            source="news",
            source_credibility=1.0,
            sentiment_score=0.0,
            event_type="Macroeconomic",
            event_confidence=0.95,
            materiality="MATERIAL_EVENT",
            evidence="Federal Reserve maintains rates and updates macroeconomic dot plot.",
        )
        res_macro = self.scorer.calculate(sig_macro_neutral)
        # Should remain high (> 6.5) because macro structural severity is high
        self.assertGreaterEqual(res_macro.impact_score, 6.5)

    def test_market_reaction_modifier(self):
        """Verify market context elevates impact score when market reaction is observed."""
        base_sig = RiskSignal(
            entity="BankCo",
            source="news",
            source_credibility=0.9,
            sentiment_score=-0.6,
            event_type="Credit Event",
            event_confidence=0.85,
            materiality="MATERIAL_EVENT",
            evidence="BankCo faces liquidity concerns.",
        )
        res_no_market = self.scorer.calculate(base_sig)

        # Add severe market dislocation context (CAR -6%, Volume 3x)
        market_sig = RiskSignal(
            entity="BankCo",
            source="news",
            source_credibility=0.9,
            sentiment_score=-0.6,
            event_type="Credit Event",
            event_confidence=0.85,
            materiality="MATERIAL_EVENT",
            market_context=MarketContext(
                abnormal_return=-0.06,
                volume_ratio=3.0,
                volatility=2.5,
            ),
            evidence="BankCo faces liquidity concerns.",
        )
        res_with_market = self.scorer.calculate(market_sig)

        self.assertGreater(res_with_market.impact_score, res_no_market.impact_score)
        self.assertGreater(res_with_market.market_modifier, 1.0)
        self.assertIn("market reaction", res_with_market.impact_reason.lower())

    def test_score_populates_signal(self):
        """Verify score() attaches impact_score and impact_reason to RiskSignal."""
        sig = RiskSignal(
            entity="MegaCorp",
            source="news",
            source_credibility=1.0,
            sentiment_score=-0.8,
            event_type="Regulatory / Legal",
            event_confidence=0.9,
            materiality="MATERIAL_EVENT",
            evidence="Regulator fines MegaCorp $1.2B for antitrust violations.",
        )
        self.assertIsNone(sig.impact_score)
        self.assertIsNone(sig.impact_reason)

        scored_sig = self.scorer.score(sig, in_place=False)
        self.assertIsNotNone(scored_sig.impact_score)
        self.assertIsNotNone(scored_sig.impact_reason)
        self.assertIsInstance(scored_sig.impact_reason, str)
        self.assertIn("Regulatory / Legal", scored_sig.impact_reason)


if __name__ == "__main__":
    unittest.main()
