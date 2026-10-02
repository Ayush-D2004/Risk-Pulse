#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic Market Data Fixture
==================================
A small, self-contained snapshot of synthetic OHLCV data that mimics the
shape yfinance returns.  Used in unit tests so they do not depend on live
network access to Yahoo Finance.

Scenario
--------
Ticker: MOCK  (hypothetical liquid stock)
Index:  ^GSPC  (broad-market proxy)
Sector: XLK    (technology sector proxy)

Date range: 2024-01-02 → 2024-02-02  (26 trading days)

The prices are constructed such that:
  - 2024-01-15 is the event anchor date (Monday, trading day)
  - 2024-01-13 is a Saturday  (weekend non-trading day)
  - 2024-01-14 is a Sunday    (weekend non-trading day)
  - Baseline = trading days 2024-01-02 → 2024-01-12  (9 trading days)
    → used in the InsufficientHistoryError test when min_baseline=10
  - For valid tests, min_baseline_days is overridden to 8 or lower.

All prices are integer-valued to make expected calculations trivial.

Exact formulas used in validation (see tests):
  stock_return  = close(2024-01-15) / close(2024-01-12) − 1
                = 110 / 100 − 1 = 0.10  (+10%)
  index_return  = 3_900 / 3_800 − 1 ≈ 0.026316
  abnormal_ret  = 0.10 − 0.026316 ≈ 0.073684
  sector_return = 190 / 180 − 1 ≈ 0.055556
  event_vol_day = 2_000_000
  baseline_vols = [1_000_000] * 9  → mean = 1_000_000
  volume_ratio  = 2_000_000 / 1_000_000 = 2.0
"""

from __future__ import annotations

from datetime import date, timezone
from typing import Dict, List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Helper to construct a DataFrame in the shape yfinance.Ticker.history returns
# ---------------------------------------------------------------------------

def _make_ohlcv(
    dates: List[date],
    closes: List[float],
    volumes: Optional[List[float]] = None,
) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with a tz-aware DatetimeIndex."""
    if volumes is None:
        volumes = [1_000_000.0] * len(dates)
    assert len(dates) == len(closes) == len(volumes)
    idx = pd.DatetimeIndex(
        [pd.Timestamp(d, tz="UTC") for d in dates], name="Date"
    )
    return pd.DataFrame(
        {
            "Open": closes,   # simplified: open = close
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": volumes,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# Baseline trading dates  (2024-01-02 to 2024-01-12  → 9 trading days)
# ---------------------------------------------------------------------------
_BASELINE_DATES = [
    date(2024, 1, 2),
    date(2024, 1, 3),
    date(2024, 1, 4),
    date(2024, 1, 5),
    date(2024, 1, 8),
    date(2024, 1, 9),
    date(2024, 1, 10),
    date(2024, 1, 11),
    date(2024, 1, 12),
]

# Event day: Monday 2024-01-15
_EVENT_DATE = date(2024, 1, 15)

_ALL_DATES = _BASELINE_DATES + [_EVENT_DATE]  # 10 dates total

# ---------------------------------------------------------------------------
# MOCK stock prices
#   Baseline: closes of 100 (flat) so log-return std = 0
#             (volatility = 0 for baseline — realistic enough for a fixture)
#   Event day: close = 110  (+10% jump)
# ---------------------------------------------------------------------------
_MOCK_CLOSES = [100.0] * len(_BASELINE_DATES) + [110.0]
_MOCK_VOLUMES = [1_000_000.0] * len(_BASELINE_DATES) + [2_000_000.0]

MOCK_STOCK_DF: pd.DataFrame = _make_ohlcv(_ALL_DATES, _MOCK_CLOSES, _MOCK_VOLUMES)

# ---------------------------------------------------------------------------
# Mock index (^GSPC proxy)
#   Baseline: 3800 flat → log-return std = 0
#   Event day: 3900  (+2.63%)
# ---------------------------------------------------------------------------
_INDEX_CLOSES = [3_800.0] * len(_BASELINE_DATES) + [3_900.0]
_INDEX_VOLUMES = [5_000_000.0] * (len(_ALL_DATES))

MOCK_INDEX_DF: pd.DataFrame = _make_ohlcv(_ALL_DATES, _INDEX_CLOSES, _INDEX_VOLUMES)

# ---------------------------------------------------------------------------
# Mock sector ETF (XLK proxy)
#   Baseline: 180 flat
#   Event day: 190  (+5.56%)
# ---------------------------------------------------------------------------
_SECTOR_CLOSES = [180.0] * len(_BASELINE_DATES) + [190.0]
_SECTOR_VOLUMES = [2_000_000.0] * len(_ALL_DATES)

MOCK_SECTOR_DF: pd.DataFrame = _make_ohlcv(_ALL_DATES, _SECTOR_CLOSES, _SECTOR_VOLUMES)

# ---------------------------------------------------------------------------
# Pre-computed expected values  (used in test assertions)
# ---------------------------------------------------------------------------
EXPECTED: Dict[str, float] = {
    # stock: close_event(110) / close_prior(100) - 1
    "stock_window_return": 0.10,
    # index: close_event(3900) / close_prior(3800) - 1
    "index_return": round(3_900 / 3_800 - 1, 6),
    # abnormal = stock − index
    "abnormal_return": round(0.10 - (3_900 / 3_800 - 1), 6),
    # volume ratio: 2_000_000 / 1_000_000
    "volume_ratio": 2.0,
    # volatility: log-returns of flat 100 baseline are all 0 → std = 0 → vol = 0
    "volatility": 0.0,
    # sector: 190/180 - 1
    "sector_movement": round(190 / 180 - 1, 6),
    # event date (UTC)
    "event_date": date(2024, 1, 15),
    "anchor_date": date(2024, 1, 15),
    "event_window_start": date(2024, 1, 15),
    "event_window_end": date(2024, 1, 15),
}
