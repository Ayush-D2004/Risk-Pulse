#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integration Tests: MarketContext ↔ ImpactScorer
================================================
Validates the five market-context integration scenarios from the design spec:

    Event          | NLP signal | Market context          | Expected behaviour
    ---------------+------------+-------------------------+--------------------
    Earnings miss  | Negative   | Strong decline + high vol | Impact increases
    Earnings miss  | Negative   | No abnormal movement    | Smaller increase
    M&A            | Positive   | Large abnormal move     | Context modifies score
    Geopolitical   | Negative   | Market confirms reaction | Higher impact
    Geopolitical   | Negative   | Market unchanged        | Don't auto-catastrophic

Key invariant:
    Market data MODIFIES the impact score — it does NOT replace event/NLP evidence.
    NLP evidence alone must already produce a meaningful baseline score.

All tests use MarketEnrichedScorer.score_with_context (offline/mock mode) so
there is no live network dependency.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.risk.impact_scorer import ImpactScorer
from src.risk.market_enriched_scorer import (
    EnrichedScoringResult,
    EnrichmentMode,
    MarketEnrichedScorer,
)
from src.risk.risk_signal import Evidence, MarketContext, RiskSignal

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)


def _make_signal(
    entity: str,
    event_type: str,
    sentiment_score: float,
    event_confidence: float = 0.91,
    source_credibility: float = 1.0,
    text: str = "Test event text.",
) -> RiskSignal:
    return RiskSignal(
        entity=entity,
        source="official",
        source_credibility=source_credibility,
        sentiment_score=sentiment_score,
        event_type=event_type,
        event_confidence=event_confidence,
        materiality="MATERIAL_EVENT",
        novelty=1.0,
        timestamp=_TS,
        evidence=Evidence(text=text),
    )


def _score_mock(
    signal: RiskSignal,
    market_context: MarketContext,
    scorer: MarketEnrichedScorer | None = None,
) -> EnrichedScoringResult:
    scorer = scorer or MarketEnrichedScorer()
    return scorer.score_with_context(signal, market_context)


def _score_raw(
    signal: RiskSignal,
    scorer: MarketEnrichedScorer | None = None,
) -> EnrichedScoringResult:
    scorer = scorer or MarketEnrichedScorer()
    return scorer.score_raw(signal)


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------


class TestMarketContextImpactIntegration(unittest.TestCase):
    """
    Validates the five market-integration behavioural requirements.
    Market data modifies — it does not replace — the NLP-driven score.
    """

    def setUp(self):
        self.scorer = MarketEnrichedScorer()

    # ------------------------------------------------------------------
    # Scenario 1: Earnings miss — market confirms → score INCREASES
    # ------------------------------------------------------------------
    def test_earnings_miss_market_confirmed_increases_score(self):
        """
        Earnings miss with negative NLP + strong abnormal decline + high volume
        must score HIGHER than the same signal without market confirmation.
        """
        signal = _make_signal(
            "RetailBank",
            "Corporate / Earnings",
            sentiment_score=-0.75,
            text="RetailBank misses EPS by 52%; guidance slashed.",
        )
        # No market context (baseline)
        raw = _score_raw(signal, self.scorer)

        # Heavy market confirmation
        heavy_ctx = MarketContext(
            abnormal_return=-0.085,  # -8.5% CAR
            volume_ratio=4.2,
            volatility=3.1,
        )
        confirmed = _score_mock(signal, heavy_ctx, self.scorer)

        self.assertGreater(
            confirmed.impact_score,
            raw.impact_score,
            msg=f"Market-confirmed ({confirmed.impact_score}) must exceed no-context ({raw.impact_score})",
        )
        self.assertGreater(confirmed.market_modifier, 1.0)
        # Market confirms, but NLP evidence was already generating a real score
        self.assertGreater(raw.impact_score, 3.0, msg="NLP alone should produce a real score > 3")

    # ------------------------------------------------------------------
    # Scenario 2: Earnings miss — no abnormal movement → smaller increase
    # ------------------------------------------------------------------
    def test_earnings_miss_no_market_move_smaller_score(self):
        """
        Earnings miss with negative NLP but FLAT market produces a
        lower score than when market confirms.
        """
        signal = _make_signal(
            "RetailBank",
            "Corporate / Earnings",
            sentiment_score=-0.75,
            text="RetailBank misses EPS by 52%; guidance slashed.",
        )
        heavy_ctx = MarketContext(
            abnormal_return=-0.085,
            volume_ratio=4.2,
            volatility=3.1,
        )
        flat_ctx = MarketContext(
            abnormal_return=0.008,   # neutral
            volume_ratio=1.1,
            volatility=1.1,
        )
        confirmed = _score_mock(signal, heavy_ctx, self.scorer)
        flat = _score_mock(signal, flat_ctx, self.scorer)

        self.assertGreater(
            confirmed.impact_score,
            flat.impact_score,
            msg=(
                f"Market-confirmed ({confirmed.impact_score}) must exceed "
                f"flat-market ({flat.impact_score})"
            ),
        )
        # Flat-market context must NOT destroy the NLP baseline score
        raw = _score_raw(signal, self.scorer)
        # Flat market should not boost significantly vs no context
        self.assertAlmostEqual(flat.impact_score, raw.impact_score, delta=0.5)

    # ------------------------------------------------------------------
    # Scenario 3: M&A — large abnormal move → context modifies upward
    # ------------------------------------------------------------------
    def test_ma_large_abnormal_move_increases_modifier(self):
        """
        M&A announcement with a +18% CAR (takeover premium) must have a
        higher market_modifier and impact_score than the same signal without
        market context.  Market data modifies the score, not replaces NLP.
        """
        signal = _make_signal(
            "PharmaCo",
            "Merger & Acquisition",
            sentiment_score=0.55,
            text="PharmaCo acquired for $22B at 38% premium.",
        )
        raw = _score_raw(signal, self.scorer)

        large_move_ctx = MarketContext(
            abnormal_return=0.18,   # +18% jump
            volume_ratio=6.5,
            volatility=2.5,
        )
        with_ctx = _score_mock(signal, large_move_ctx, self.scorer)

        self.assertGreater(with_ctx.market_modifier, raw.market_modifier)
        self.assertGreater(with_ctx.impact_score, raw.impact_score)
        # NLP alone should still give a reasonable M&A score
        self.assertGreater(raw.impact_score, 4.0)

    # ------------------------------------------------------------------
    # Scenario 4: Geopolitical — market confirms → higher impact
    # ------------------------------------------------------------------
    def test_geopolitical_market_confirms_higher_impact(self):
        """
        Geopolitical negative signal + confirmed market reaction must produce
        a higher impact than the same signal with a flat market.
        """
        signal = _make_signal(
            "EnergyMajor",
            "Geopolitical",
            sentiment_score=-0.72,
            text="New sanctions target EnergyMajor oil exports.",
        )
        mkt_reaction_ctx = MarketContext(
            abnormal_return=-0.065,
            volume_ratio=3.8,
            volatility=2.7,
        )
        flat_ctx = MarketContext(
            abnormal_return=0.003,
            volume_ratio=1.05,
            volatility=0.8,
        )
        confirmed = _score_mock(signal, mkt_reaction_ctx, self.scorer)
        flat = _score_mock(signal, flat_ctx, self.scorer)

        self.assertGreater(
            confirmed.impact_score,
            flat.impact_score,
            msg=(
                f"Market-confirmed geopolitical ({confirmed.impact_score}) must "
                f"exceed flat-market ({flat.impact_score})"
            ),
        )
        self.assertGreater(confirmed.market_modifier, 1.0)

    # ------------------------------------------------------------------
    # Scenario 5: Geopolitical — market unchanged → NOT automatically catastrophic
    # ------------------------------------------------------------------
    def test_geopolitical_market_unchanged_not_catastrophic(self):
        """
        A geopolitical event where the market does not react must NOT
        automatically receive the top impact tier (≥ 9.0), even with
        strongly negative NLP sentiment.

        This enforces the design invariant: market data MODIFIES impact;
        NLP + event severity set the structural baseline.  A muted market
        response should neither boost the score to catastrophic levels nor
        destroy the NLP baseline.
        """
        signal = _make_signal(
            "EnergyMajor",
            "Geopolitical",
            sentiment_score=-0.72,
            text="New sanctions target EnergyMajor oil exports.",
        )
        flat_ctx = MarketContext(
            abnormal_return=0.008,
            volume_ratio=1.05,
            volatility=1.1,
        )
        flat = _score_mock(signal, flat_ctx, self.scorer)

        # Must NOT be automatically catastrophic
        self.assertLess(
            flat.impact_score,
            9.0,
            msg=(
                f"Geopolitical with muted market should not score ≥ 9.0; "
                f"got {flat.impact_score}"
            ),
        )
        # But should still be a meaningful geopolitical score
        self.assertGreater(
            flat.impact_score,
            3.0,
            msg="Geopolitical NLP baseline should be > 3.0 even without market confirmation",
        )
        # Market modifier should be near neutral
        self.assertAlmostEqual(flat.market_modifier, 1.0, delta=0.05)


class TestMarketEnrichedScorerModes(unittest.TestCase):
    """Unit tests for the three enrichment modes of MarketEnrichedScorer."""

    def test_score_raw_returns_skip_mode(self):
        signal = _make_signal("Corp", "Credit Event", sentiment_score=-0.8)
        scorer = MarketEnrichedScorer()
        result = scorer.score_raw(signal)
        self.assertEqual(result.enrichment_mode, EnrichmentMode.SKIP)
        self.assertIsNone(result.enriched_signal.market_context)
        self.assertAlmostEqual(result.market_modifier, 1.0)

    def test_score_with_context_returns_mock_mode(self):
        signal = _make_signal("Corp", "Credit Event", sentiment_score=-0.8)
        ctx = MarketContext(abnormal_return=-0.05, volume_ratio=2.5)
        scorer = MarketEnrichedScorer()
        result = scorer.score_with_context(signal, ctx)
        self.assertEqual(result.enrichment_mode, EnrichmentMode.MOCK)
        self.assertIsNotNone(result.enriched_signal.market_context)

    def test_score_with_none_context_returns_skip_modifier(self):
        """Passing None market_context must keep market_modifier at 1.0."""
        signal = _make_signal("Corp", "Credit Event", sentiment_score=-0.8)
        scorer = MarketEnrichedScorer()
        result = scorer.score_with_context(signal, market_context=None)
        self.assertAlmostEqual(result.market_modifier, 1.0)

    def test_original_signal_is_not_mutated(self):
        """score_with_context must not mutate the original signal."""
        signal = _make_signal("Corp", "Credit Event", sentiment_score=-0.8)
        original_ctx = signal.market_context  # None
        scorer = MarketEnrichedScorer()
        ctx = MarketContext(abnormal_return=-0.06)
        scorer.score_with_context(signal, ctx)
        self.assertEqual(signal.market_context, original_ctx)

    def test_enriched_scorer_live_fails_gracefully_with_bad_ticker(self):
        """
        score_live with an empty ticker must not raise when on_error='warn'.
        The result should fall back to market_modifier=1.0.
        """
        signal = _make_signal("Corp", "Credit Event", sentiment_score=-0.8)
        scorer = MarketEnrichedScorer()
        result = scorer.score_live(signal, ticker="", on_error="warn")
        self.assertIsNotNone(result.enrichment_error)
        self.assertAlmostEqual(result.market_modifier, 1.0)
        self.assertEqual(result.enrichment_mode, EnrichmentMode.LIVE)

    def test_summary_string(self):
        signal = _make_signal("Corp", "Credit Event", sentiment_score=-0.8)
        scorer = MarketEnrichedScorer()
        result = scorer.score_raw(signal)
        s = result.summary()
        self.assertIsInstance(s, str)
        self.assertIn("Corp", s)
        self.assertIn("score=", s)


class TestMarketModifierDoesNotReplaceNLP(unittest.TestCase):
    """
    Verify the core design invariant: market context MODIFIES but does NOT
    replace the NLP / event-severity signal.

    A strongly negative event should score high even with no market context.
    A minor event should stay low even with a large market move.
    """

    def test_credit_event_stays_high_without_market_context(self):
        """High-severity credit event must score high with no market data."""
        signal = _make_signal(
            "DebtCo",
            "Credit Event",
            sentiment_score=-0.9,
            event_confidence=0.95,
        )
        scorer = MarketEnrichedScorer()
        result = scorer.score_raw(signal)
        self.assertGreaterEqual(result.impact_score, 7.0)

    def test_minor_event_stays_low_despite_large_market_move(self):
        """
        A low-severity product event should NOT be inflated to 'High Impact'
        purely by a large market modifier.  NLP + event severity drive the base.
        """
        signal = _make_signal(
            "AppCo",
            "Product / Technology",
            sentiment_score=0.6,
            event_confidence=0.55,
        )
        scorer = MarketEnrichedScorer()
        # Inject a very large market move
        large_ctx = MarketContext(
            abnormal_return=0.20,   # +20% — huge move
            volume_ratio=8.0,
            volatility=3.5,
        )
        result = scorer.score_with_context(signal, large_ctx)
        # Market modifier is at max 1.30; low base severity caps the score
        self.assertLess(
            result.impact_score,
            7.0,
            msg=(
                f"Minor product event must stay < 7.0 even with large market move; "
                f"got {result.impact_score} (mkt_mod={result.market_modifier})"
            ),
        )

    def test_market_modifier_is_bounded(self):
        """Market modifier must always be in [0.70, 1.30]."""
        scorer_base = ImpactScorer()
        extreme_ctx = MarketContext(
            abnormal_return=-0.50,   # -50% (extreme)
            volume_ratio=100.0,       # unrealistic volume spike
            volatility=99.9,
        )
        mod = scorer_base.compute_market_modifier(extreme_ctx)
        self.assertGreaterEqual(mod, 0.70)
        self.assertLessEqual(mod, 1.30)

        zero_ctx = MarketContext(
            abnormal_return=0.0,
            volume_ratio=0.5,
            volatility=0.1,
        )
        mod_zero = scorer_base.compute_market_modifier(zero_ctx)
        self.assertGreaterEqual(mod_zero, 0.70)
        self.assertLessEqual(mod_zero, 1.30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
