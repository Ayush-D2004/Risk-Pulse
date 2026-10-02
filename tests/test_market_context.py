#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests for src/market/market_context.py
============================================
All tests are fully deterministic: live yfinance calls are patched with the
cached fixture data from tests/market_fixtures.py so the suite can run
offline and in CI without network access.

Test Coverage
-------------
1. valid_liquid_stock           – full happy-path, validates all five fields
2. weekend_event                – Saturday event → rolls back to Friday anchor
3. missing_ticker               – empty or unknown ticker raises TickerResolutionError
4. insufficient_history         – fewer baseline days than min raises InsufficientHistoryError
5. missing_volume               – Volume column absent → volume_ratio is None
6. market_holiday               – event on a US holiday → rolls back to prior trading day
7. benchmark_unavailable        – index fetch fails → warning issued, abnormal_return = raw return
8. fixture_deterministic        – direct formula validation against pre-computed EXPECTED values
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pandas as pd

from src.market.market_context import (
    InsufficientHistoryError,
    MarketContextConfig,
    MarketContextFetcher,
    MarketContextResult,
    MarketDataError,
    NoTradingSessionError,
    TickerResolutionError,
    _compute_realized_volatility,
    _compute_volume_ratio,
    _compute_window_return,
    _locate_anchor_date,
)
from src.risk.risk_signal import MarketContext
from tests.market_fixtures import (
    EXPECTED,
    MOCK_INDEX_DF,
    MOCK_SECTOR_DF,
    MOCK_STOCK_DF,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_EVENT_TS = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
_WEEKEND_TS = datetime(2024, 1, 13, 14, 30, 0, tzinfo=timezone.utc)   # Saturday
_HOLIDAY_TS = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)      # New Year's Day

# Config that matches the 9-day baseline in our fixture (min_baseline=8)
_VALID_CFG = MarketContextConfig(
    event_window_days=1,
    baseline_days=9,
    min_baseline_days=8,
    volatility_window=9,
)


def _make_fetcher(cfg: Optional[MarketContextConfig] = None) -> MarketContextFetcher:
    return MarketContextFetcher(cfg or _VALID_CFG)


def _patch_fetch(stock_df=MOCK_STOCK_DF, index_df=MOCK_INDEX_DF, sector_df=MOCK_SECTOR_DF):
    """
    Return a context manager that patches _fetch_ohlcv to return fixture data.
    The first call returns stock_df, second index_df, optional third sector_df.
    """
    call_seq = [stock_df, index_df, sector_df]
    call_count = {"n": 0}

    def side_effect(ticker, start, end):
        idx = call_count["n"]
        call_count["n"] += 1
        df = call_seq[idx % len(call_seq)]
        if df is None:
            raise TickerResolutionError(f"No data for ticker '{ticker}'")
        return df

    return patch(
        "src.market.market_context._fetch_ohlcv",
        side_effect=side_effect,
    )


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------


class TestMarketContextFetcher(unittest.TestCase):
    """Unit tests for MarketContextFetcher, fully offline via fixture mocks."""

    # ------------------------------------------------------------------
    # 1. Valid liquid stock — happy path
    # ------------------------------------------------------------------
    def test_valid_liquid_stock(self):
        """
        Full happy-path: all five MarketContext fields are populated correctly.
        Validates types, ranges, and sign conventions.
        """
        fetcher = _make_fetcher()
        with _patch_fetch():
            result = fetcher.fetch(
                ticker="MOCK",
                event_timestamp=_EVENT_TS,
                sector="technology",
            )

        self.assertIsInstance(result, MarketContextResult)
        ctx = result.market_context
        self.assertIsInstance(ctx, MarketContext)

        # abnormal_return: stock (+10%) − index (+2.63%) ≈ +7.37%
        self.assertIsNotNone(ctx.abnormal_return)
        self.assertAlmostEqual(ctx.abnormal_return, EXPECTED["abnormal_return"], places=4)
        self.assertGreater(ctx.abnormal_return, 0)

        # index_movement: +2.63%
        self.assertIsNotNone(ctx.index_movement)
        self.assertAlmostEqual(ctx.index_movement, EXPECTED["index_return"], places=4)

        # volume_ratio: 2.0
        self.assertIsNotNone(ctx.volume_ratio)
        self.assertAlmostEqual(ctx.volume_ratio, EXPECTED["volume_ratio"], places=4)
        self.assertGreater(ctx.volume_ratio, 1.0)

        # volatility: 0.0 (flat baseline prices → 0 log-return std)
        self.assertIsNotNone(ctx.volatility)
        self.assertAlmostEqual(ctx.volatility, EXPECTED["volatility"], places=6)

        # sector_movement: +5.56%
        self.assertIsNotNone(ctx.sector_movement)
        self.assertAlmostEqual(ctx.sector_movement, EXPECTED["sector_movement"], places=4)

        # Audit metadata — observation window
        meta = ctx.metadata
        self.assertIn("observation_window", meta)
        self.assertEqual(
            meta["observation_window"]["event_window_start"],
            EXPECTED["event_window_start"].isoformat(),
        )
        self.assertEqual(
            meta["observation_window"]["event_window_end"],
            EXPECTED["event_window_end"].isoformat(),
        )

        # Result-level audit fields
        self.assertEqual(result.ticker, "MOCK")
        self.assertEqual(result.anchor_date, EXPECTED["anchor_date"])
        self.assertEqual(result.sector_ticker, "XLK")
        self.assertEqual(result.index_ticker, "^GSPC")

    # ------------------------------------------------------------------
    # 2. Weekend event — anchor rolls back to previous Friday
    # ------------------------------------------------------------------
    def test_weekend_event(self):
        """
        Event timestamp on a Saturday (2024-01-13).
        Anchor date must be the prior Friday (2024-01-12).
        The event window is a single day: Friday 2024-01-12.
        """
        fetcher = _make_fetcher()
        with _patch_fetch():
            result = fetcher.fetch(
                ticker="MOCK",
                event_timestamp=_WEEKEND_TS,  # Saturday 2024-01-13
            )

        # Anchor must be the last trading day ≤ Saturday → Friday 2024-01-12
        self.assertEqual(result.anchor_date, date(2024, 1, 12))
        self.assertEqual(result.event_window_end, date(2024, 1, 12))

        # Event-window close: 100 (the flat baseline price on 2024-01-12)
        # Prior close also 100 → return = 0
        ctx = result.market_context
        # No sector passed: sector_movement is None
        self.assertIsNone(ctx.sector_movement)

    # ------------------------------------------------------------------
    # 3. Missing ticker
    # ------------------------------------------------------------------
    def test_missing_ticker_empty_string(self):
        """Empty ticker string must raise TickerResolutionError immediately."""
        fetcher = _make_fetcher()
        with self.assertRaises(TickerResolutionError):
            fetcher.fetch(ticker="", event_timestamp=_EVENT_TS)

    def test_missing_ticker_whitespace(self):
        """Whitespace-only ticker must raise TickerResolutionError."""
        fetcher = _make_fetcher()
        with self.assertRaises(TickerResolutionError):
            fetcher.fetch(ticker="   ", event_timestamp=_EVENT_TS)

    def test_missing_ticker_unknown(self):
        """Unknown ticker (yfinance returns empty DataFrame) raises TickerResolutionError."""
        fetcher = _make_fetcher()
        with _patch_fetch(stock_df=None):
            with self.assertRaises(TickerResolutionError):
                fetcher.fetch(ticker="XXXXNOTREAL", event_timestamp=_EVENT_TS)

    # ------------------------------------------------------------------
    # 4. Insufficient history
    # ------------------------------------------------------------------
    def test_insufficient_history(self):
        """
        When min_baseline_days=10 but only 9 pre-event trading days exist
        in the fixture, InsufficientHistoryError must be raised.
        """
        cfg = MarketContextConfig(
            event_window_days=1,
            baseline_days=10,
            min_baseline_days=10,
            volatility_window=10,
        )
        fetcher = _make_fetcher(cfg)
        # fixture has 9 baseline days + 1 event day = 10 total trading days
        # event window claims 1 day (2024-01-15), leaving 9 pre-event days
        # → 9 < min_baseline_days=10 → should raise
        with _patch_fetch():
            with self.assertRaises(InsufficientHistoryError):
                fetcher.fetch(ticker="MOCK", event_timestamp=_EVENT_TS)

    # ------------------------------------------------------------------
    # 5. Missing volume
    # ------------------------------------------------------------------
    def test_missing_volume(self):
        """
        If the Volume column is absent from the OHLCV DataFrame,
        volume_ratio must be None and a warning must be recorded.
        """
        no_vol_df = MOCK_STOCK_DF.drop(columns=["Volume"])
        fetcher = _make_fetcher()
        with _patch_fetch(stock_df=no_vol_df):
            result = fetcher.fetch(ticker="MOCK", event_timestamp=_EVENT_TS)

        ctx = result.market_context
        self.assertIsNone(ctx.volume_ratio)
        # A warning must have been recorded
        self.assertTrue(
            any("Volume" in w or "volume" in w for w in result.warnings),
            msg=f"Expected volume warning, got: {result.warnings}",
        )

    # ------------------------------------------------------------------
    # 6. Market holiday — event falls on 2024-01-01 (New Year's Day)
    # ------------------------------------------------------------------
    def test_market_holiday(self):
        """
        Event on a market holiday (2024-01-01).  The fixture has no entry
        for 2024-01-01.  Anchor must roll back to the last trading day
        that is in the downloaded DataFrame (2023-12-29).
        Three rows are needed: 2 pre-event baseline + 1 event anchor.
        """
        # Dates in ascending order (as yfinance returns them)
        holiday_dates = [
            date(2023, 12, 27),   # baseline day 1
            date(2023, 12, 28),   # baseline day 2
            date(2023, 12, 29),   # last trading day before the holiday
        ]
        holiday_closes = [98.0, 99.0, 100.0]
        holiday_df = pd.DataFrame(
            {
                "Open": holiday_closes,
                "High": holiday_closes,
                "Low": holiday_closes,
                "Close": holiday_closes,
                "Volume": [1_000_000.0, 1_000_000.0, 1_200_000.0],
            },
            index=pd.DatetimeIndex(
                [pd.Timestamp(d, tz="UTC") for d in holiday_dates], name="Date"
            ),
        )
        # event_window_days=1 → anchor is 2023-12-29
        # pre_event_days before 2023-12-29 → [2023-12-27, 2023-12-28] = 2 days
        # min_baseline=1 is satisfied
        cfg = MarketContextConfig(
            event_window_days=1,
            baseline_days=2,
            min_baseline_days=1,
            volatility_window=2,
        )
        fetcher = _make_fetcher(cfg)
        with _patch_fetch(stock_df=holiday_df):
            result = fetcher.fetch(
                ticker="MOCK",
                event_timestamp=_HOLIDAY_TS,  # 2024-01-01
            )

        # Anchor must be 2023-12-29 (last trading day ≤ 2024-01-01 in fixture)
        self.assertEqual(result.anchor_date, date(2023, 12, 29))

    # ------------------------------------------------------------------
    # 7. Benchmark data unavailable
    # ------------------------------------------------------------------
    def test_benchmark_data_unavailable(self):
        """
        When the broad-market index cannot be fetched, the fetcher must:
          - Not raise (non-fatal)
          - Set index_movement to None
          - Set abnormal_return to the raw stock return (with a warning)
          - Record a descriptive warning in the result
        """
        fetcher = _make_fetcher()

        # First call: stock data OK; second call: index fails
        call_count = {"n": 0}
        def side_effect(ticker, start, end):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return MOCK_STOCK_DF      # stock OK
            raise TickerResolutionError("Simulated index fetch failure")

        with patch("src.market.market_context._fetch_ohlcv", side_effect=side_effect):
            result = fetcher.fetch(ticker="MOCK", event_timestamp=_EVENT_TS)

        ctx = result.market_context
        # index_movement must be None
        self.assertIsNone(ctx.index_movement)
        # abnormal_return falls back to raw stock return
        self.assertIsNotNone(ctx.abnormal_return)
        self.assertAlmostEqual(ctx.abnormal_return, 0.10, places=4)
        # Warning must mention the benchmark
        self.assertTrue(
            any("benchmark" in w.lower() or "index" in w.lower() for w in result.warnings),
            msg=f"Expected benchmark warning, got: {result.warnings}",
        )

    # ------------------------------------------------------------------
    # 8. Fixture deterministic validation
    # ------------------------------------------------------------------
    def test_fixture_deterministic_formulas(self):
        """
        Validate pre-computed EXPECTED values directly against the helper
        functions to ensure the fixture arithmetic is self-consistent.
        """
        # -- window return for stock
        close = MOCK_STOCK_DF["Close"]
        event_ts = pd.Timestamp("2024-01-15", tz="UTC")
        window_start_ts = pd.Timestamp("2024-01-15", tz="UTC")

        stock_ret = _compute_window_return(close, window_start_ts, event_ts)
        self.assertAlmostEqual(stock_ret, EXPECTED["stock_window_return"], places=6)

        # -- window return for index
        idx_close = MOCK_INDEX_DF["Close"]
        idx_ret = _compute_window_return(idx_close, window_start_ts, event_ts)
        self.assertAlmostEqual(idx_ret, EXPECTED["index_return"], places=6)

        # -- abnormal return = stock − index
        expected_abnormal = EXPECTED["stock_window_return"] - EXPECTED["index_return"]
        self.assertAlmostEqual(
            EXPECTED["abnormal_return"], expected_abnormal, places=6
        )

        # -- volume ratio
        vol_series = MOCK_STOCK_DF["Volume"]
        baseline_mask = MOCK_STOCK_DF.index < event_ts
        vol_ratio = _compute_volume_ratio(vol_series, event_ts, baseline_mask)
        self.assertAlmostEqual(vol_ratio, EXPECTED["volume_ratio"], places=4)

        # -- volatility (flat baseline → std of log-returns = 0)
        baseline_mask2 = MOCK_STOCK_DF.index < event_ts
        vol = _compute_realized_volatility(close, baseline_mask2, 252)
        self.assertAlmostEqual(vol, EXPECTED["volatility"], places=6)

        # -- sector return
        sec_close = MOCK_SECTOR_DF["Close"]
        sec_ret = _compute_window_return(sec_close, window_start_ts, event_ts)
        self.assertAlmostEqual(sec_ret, EXPECTED["sector_movement"], places=6)

    # ------------------------------------------------------------------
    # 9. Config validation
    # ------------------------------------------------------------------
    def test_config_validation_bad_window(self):
        with self.assertRaises(ValueError):
            MarketContextConfig(event_window_days=0)

    def test_config_validation_vol_exceeds_baseline(self):
        with self.assertRaises(ValueError):
            MarketContextConfig(baseline_days=10, min_baseline_days=5, volatility_window=15)

    # ------------------------------------------------------------------
    # 10. MarketContextResult.to_dict is fully serialisable
    # ------------------------------------------------------------------
    def test_result_to_dict_serialisable(self):
        """to_dict() must return a plain dict with only JSON-safe types."""
        import json
        fetcher = _make_fetcher()
        with _patch_fetch():
            result = fetcher.fetch(
                ticker="MOCK",
                event_timestamp=_EVENT_TS,
                sector="technology",
            )
        d = result.to_dict()
        self.assertIsInstance(d, dict)
        # Must be JSON-serialisable without custom encoders
        json_str = json.dumps(d)
        self.assertIsInstance(json_str, str)

    # ------------------------------------------------------------------
    # 11. Sector lookup — unmapped sector emits a warning, returns None
    # ------------------------------------------------------------------
    def test_unmapped_sector_returns_none_with_warning(self):
        """An unknown sector name should not raise; sector_movement = None."""
        fetcher = _make_fetcher()
        with _patch_fetch():
            result = fetcher.fetch(
                ticker="MOCK",
                event_timestamp=_EVENT_TS,
                sector="XYZ_UNKNOWN_SECTOR",
            )
        ctx = result.market_context
        self.assertIsNone(ctx.sector_movement)
        self.assertTrue(
            any("sector" in w.lower() for w in result.warnings),
            msg=f"Expected sector warning, got: {result.warnings}",
        )

    # ------------------------------------------------------------------
    # 12. No-sector call: sector_movement = None (no warning expected)
    # ------------------------------------------------------------------
    def test_no_sector_argument(self):
        """When sector is not provided, sector_movement must be None."""
        fetcher = _make_fetcher()
        with _patch_fetch():
            result = fetcher.fetch(
                ticker="MOCK",
                event_timestamp=_EVENT_TS,
                # sector=None by default
            )
        self.assertIsNone(result.market_context.sector_movement)
        self.assertIsNone(result.sector_ticker)

    # ------------------------------------------------------------------
    # 13. MarketContext integrates with RiskSignal
    # ------------------------------------------------------------------
    def test_market_context_compatible_with_risk_signal(self):
        """The MarketContext returned must be assignable to RiskSignal.market_context."""
        from src.risk.risk_signal import Evidence, RiskSignal

        fetcher = _make_fetcher()
        with _patch_fetch():
            result = fetcher.fetch(ticker="MOCK", event_timestamp=_EVENT_TS)

        signal = RiskSignal(
            entity="MOCK Corp",
            source="twitter",
            sentiment_score=-0.5,
            event_type="Corporate / Earnings",
            event_confidence=0.85,
            materiality="MATERIAL_EVENT",
            evidence=Evidence(text="Earnings miss announced"),
            market_context=result.market_context,
        )
        self.assertIsNotNone(signal.market_context)
        self.assertAlmostEqual(
            signal.market_context.abnormal_return,
            EXPECTED["abnormal_return"],
            places=4,
        )


class TestInternalHelpers(unittest.TestCase):
    """Direct unit tests for internal calculation helpers."""

    def test_locate_anchor_date_trading_day(self):
        """anchor_date equals event_date when event_date is a trading day."""
        df = MOCK_STOCK_DF
        anchor = _locate_anchor_date(df, date(2024, 1, 15))
        self.assertEqual(anchor.date(), date(2024, 1, 15))

    def test_locate_anchor_date_weekend(self):
        """anchor_date rolls back to Friday when event_date is a Saturday."""
        df = MOCK_STOCK_DF
        anchor = _locate_anchor_date(df, date(2024, 1, 13))  # Saturday
        self.assertEqual(anchor.date(), date(2024, 1, 12))   # Friday

    def test_compute_volume_ratio_zero_event_vol(self):
        """volume_ratio is None when event-day volume is 0."""
        dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]
        idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])
        vols = pd.Series([1_000_000.0, 1_000_000.0, 0.0], index=idx)
        event_ts = pd.Timestamp(date(2024, 1, 4), tz="UTC")
        baseline_mask = idx < event_ts
        result = _compute_volume_ratio(vols, event_ts, baseline_mask)
        self.assertIsNone(result)

    def test_compute_volume_ratio_no_baseline(self):
        """volume_ratio is None when baseline is empty."""
        dates = [date(2024, 1, 2)]
        idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])
        vols = pd.Series([2_000_000.0], index=idx)
        event_ts = pd.Timestamp(date(2024, 1, 2), tz="UTC")
        baseline_mask = idx < event_ts  # no prior days
        result = _compute_volume_ratio(vols, event_ts, baseline_mask)
        self.assertIsNone(result)

    def test_compute_realized_vol_insufficient(self):
        """Volatility is None when fewer than 2 observations exist."""
        dates = [date(2024, 1, 2)]
        idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])
        close = pd.Series([100.0], index=idx)
        mask = pd.Series([True], index=idx)
        vol = _compute_realized_volatility(close, mask, 252)
        self.assertIsNone(vol)

    def test_compute_window_return_simple(self):
        """window_return = end_close / prior_close - 1."""
        dates = [date(2024, 1, 2), date(2024, 1, 3)]
        idx = pd.DatetimeIndex([pd.Timestamp(d, tz="UTC") for d in dates])
        close = pd.Series([100.0, 110.0], index=idx)
        start_ts = pd.Timestamp(date(2024, 1, 3), tz="UTC")
        end_ts = pd.Timestamp(date(2024, 1, 3), tz="UTC")
        r = _compute_window_return(close, start_ts, end_ts)
        self.assertAlmostEqual(r, 0.10, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
