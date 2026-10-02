#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market Context Module
=====================
Retrieves historical market data via yfinance and calculates the five
quantitative market-context fields required by the MarketContext schema
(defined in src/risk/risk_signal.py):

    abnormal_return   – event-window stock return minus index return
    volume_ratio      – event-day volume / rolling baseline average volume
    volatility        – rolling historical realized volatility
    sector_movement   – sector ETF return over the same event window
    index_movement    – broad-market index return over the event window

Design Principles
-----------------
* No look-ahead leakage: only data available at or before the event
  timestamp is used for features. Future-return columns (1_DAY_RETURN,
  2_DAY_RETURN, …) are NEVER read or referenced here.
* Explicit failure modes: weekends, holidays, missing tickers, and API
  failures all raise typed exceptions rather than silently returning
  wrong numbers.
* Configurable windows: event-window days, baseline days, and volatility
  window are all constructor parameters, not magic constants.
* Provider-agnostic interface: the fetcher wraps yfinance; the rest of
  the codebase sees only MarketContextResult / MarketContext.

Terminology
-----------
* event_date     – calendar date extracted from the event timestamp.
* anchor_date    – the last *trading* day on or before event_date.
* event_window   – [anchor_date − (window_days − 1), anchor_date]
                   (inclusive). A window_days=1 means just anchor_date.
* baseline       – the baseline_days trading days *before* event_window
                   used for volume and volatility references.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# yfinance — required; callers handle ImportError if absent
try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YF_AVAILABLE = False

from src.risk.risk_signal import MarketContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public exception hierarchy
# ---------------------------------------------------------------------------


class MarketDataError(Exception):
    """Base exception for all market-context retrieval failures."""


class TickerResolutionError(MarketDataError):
    """Raised when the ticker is unknown, empty, or explicitly invalid."""


class InsufficientHistoryError(MarketDataError):
    """Raised when fewer trading days than required are available."""


class BenchmarkUnavailableError(MarketDataError):
    """Raised when benchmark / index data cannot be retrieved."""


class NoTradingSessionError(MarketDataError):
    """Raised when the event date falls on a weekend or market holiday."""


# ---------------------------------------------------------------------------
# Sector → ETF mapping  (GICS-level approximation via SPDR sector ETFs)
# ---------------------------------------------------------------------------

SECTOR_ETF_MAP: Dict[str, str] = {
    "technology": "XLK",
    "financials": "XLF",
    "healthcare": "XLV",
    "consumer discretionary": "XLY",
    "consumer staples": "XLP",
    "energy": "XLE",
    "utilities": "XLU",
    "real estate": "XLRE",
    "materials": "XLB",
    "industrials": "XLI",
    "communication services": "XLC",
    "communications": "XLC",
    # Common aliases
    "info tech": "XLK",
    "information technology": "XLK",
    "health care": "XLV",
    "cons disc": "XLY",
    "cons staples": "XLP",
}

# Default broad-market benchmark
DEFAULT_INDEX_TICKER = "^GSPC"  # S&P 500


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class MarketContextConfig:
    """
    All configurable parameters for market-context calculation.

    Attributes
    ----------
    event_window_days : int
        Number of *trading* days in the event window (inclusive of the
        anchor date).  1 = single-day event window.  Default: 1.
    baseline_days : int
        Number of trading days *before* the event window used to compute
        the volume baseline and volatility.  Default: 20.
    min_baseline_days : int
        Minimum acceptable trading days in the baseline period.  If fewer
        days are found, InsufficientHistoryError is raised.  Default: 10.
    volatility_window : int
        Number of trading days used for rolling annualised realized
        volatility.  Must be ≤ baseline_days.  Default: 20.
    volatility_annualisation_factor : int
        Trading days per year for annualisation.  Default: 252.
    index_ticker : str
        Yahoo Finance ticker for the broad-market benchmark.  Default: "^GSPC".
    sector_etf_map : Dict[str, str]
        Mapping from sector name (lowercase) to Yahoo Finance ETF ticker.
    """

    event_window_days: int = 1
    baseline_days: int = 20
    min_baseline_days: int = 10
    volatility_window: int = 20
    volatility_annualisation_factor: int = 252
    index_ticker: str = DEFAULT_INDEX_TICKER
    sector_etf_map: Dict[str, str] = field(
        default_factory=lambda: dict(SECTOR_ETF_MAP)
    )

    def __post_init__(self) -> None:
        if self.event_window_days < 1:
            raise ValueError("event_window_days must be >= 1")
        if self.baseline_days < self.min_baseline_days:
            raise ValueError(
                f"baseline_days ({self.baseline_days}) must be >= "
                f"min_baseline_days ({self.min_baseline_days})"
            )
        if self.volatility_window > self.baseline_days:
            raise ValueError(
                f"volatility_window ({self.volatility_window}) must be <= "
                f"baseline_days ({self.baseline_days})"
            )


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class MarketContextResult:
    """
    Full output of a market-context calculation, including both the
    structured MarketContext object and the audit metadata.

    Attributes
    ----------
    market_context : MarketContext
        Pydantic model compatible with RiskSignal.market_context.
    ticker : str
        The ticker symbol actually queried.
    event_timestamp : datetime
        The original event timestamp (UTC).
    anchor_date : date
        Last trading day on or before the event date used as event anchor.
    event_window_start : date
        First day of the event window (inclusive).
    event_window_end : date
        Last day of the event window (inclusive = anchor_date).
    baseline_start : date
        First day of the baseline period (inclusive).
    baseline_end : date
        Last day of the baseline period (inclusive).
    index_ticker : str
        The broad-market benchmark ticker used.
    sector_ticker : Optional[str]
        The sector ETF ticker used, or None if not available.
    warnings : List[str]
        Non-fatal issues encountered during calculation (e.g., missing
        sector data, volume missing for some days).
    """

    market_context: MarketContext
    ticker: str
    event_timestamp: datetime
    anchor_date: date
    event_window_start: date
    event_window_end: date
    baseline_start: date
    baseline_end: date
    index_ticker: str
    sector_ticker: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dictionary of this result."""
        return {
            "market_context": self.market_context.model_dump(),
            "ticker": self.ticker,
            "event_timestamp": self.event_timestamp.isoformat(),
            "anchor_date": self.anchor_date.isoformat(),
            "event_window_start": self.event_window_start.isoformat(),
            "event_window_end": self.event_window_end.isoformat(),
            "baseline_start": self.baseline_start.isoformat(),
            "baseline_end": self.baseline_end.isoformat(),
            "index_ticker": self.index_ticker,
            "sector_ticker": self.sector_ticker,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_utc_date(ts: datetime) -> date:
    """Convert an event timestamp to a UTC calendar date."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).date()


def _fetch_ohlcv(
    ticker: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """
    Download daily OHLCV data for *ticker* in [start, end] (inclusive).

    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    Index is a DatetimeIndex in UTC.

    Raises
    ------
    MarketDataError
        If yfinance is unavailable or the download fails.
    TickerResolutionError
        If the returned DataFrame is empty (ticker not found).
    """
    if not _YF_AVAILABLE:  # pragma: no cover
        raise MarketDataError(
            "yfinance is not installed. Install it with: pip install yfinance"
        )

    if not ticker or not ticker.strip():
        raise TickerResolutionError("ticker must be a non-empty string")

    # yfinance end is exclusive — add one day
    yf_end = end + timedelta(days=1)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tkr = yf.Ticker(ticker)
            df = tkr.history(
                start=start.isoformat(),
                end=yf_end.isoformat(),
                auto_adjust=True,
                repair=False,
            )
    except Exception as exc:
        raise MarketDataError(
            f"yfinance download failed for '{ticker}': {exc}"
        ) from exc

    if df is None or df.empty:
        raise TickerResolutionError(
            f"No market data returned for ticker '{ticker}' "
            f"between {start} and {end}. The ticker may be invalid, "
            f"delisted, or the date range falls entirely outside trading sessions."
        )

    # Normalise timezone: ensure index is tz-aware UTC dates
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    # Keep only needed columns (yfinance column names may vary)
    cols_wanted = {"Open", "High", "Low", "Close", "Volume"}
    cols_present = {c for c in df.columns if c in cols_wanted}
    df = df[sorted(cols_present, key=list(cols_wanted).index)]

    return df


def _find_trading_days(df: pd.DataFrame) -> pd.DatetimeIndex:
    """Return the DatetimeIndex of the DataFrame (trading days only)."""
    return df.index


def _locate_anchor_date(
    df: pd.DataFrame,
    event_date: date,
) -> pd.Timestamp:
    """
    Find the last trading day in *df* that is on or before *event_date*.

    Raises
    ------
    NoTradingSessionError
        If no trading day at or before event_date exists in *df*.
    """
    cutoff = pd.Timestamp(event_date, tz="UTC")
    trading_on_or_before = df.index[df.index <= cutoff]
    if trading_on_or_before.empty:
        raise NoTradingSessionError(
            f"No trading sessions found on or before {event_date} in the "
            f"downloaded data. The event may fall on or before the data range."
        )
    return trading_on_or_before[-1]


def _compute_window_return(
    close_series: pd.Series,
    window_start_ts: pd.Timestamp,
    window_end_ts: pd.Timestamp,
) -> float:
    """
    Calculate the cumulative return over [window_start_ts, window_end_ts].

    Formula
    -------
        R = close(window_end) / close(window_start_prior) − 1

    where close(window_start_prior) is the closing price of the trading
    day *immediately before* window_start_ts (i.e. the reference close).

    If window_start_ts is the earliest available trading day (no prior
    close), we fall back to open-to-close return for that day.
    """
    # Subset to window
    mask = (close_series.index >= window_start_ts) & (
        close_series.index <= window_end_ts
    )
    window_closes = close_series[mask]

    if window_closes.empty:
        raise InsufficientHistoryError(
            f"No close prices found in window [{window_start_ts.date()}, "
            f"{window_end_ts.date()}]."
        )

    end_close = window_closes.iloc[-1]

    # Find the close just before window_start
    prior_mask = close_series.index < window_start_ts
    prior_closes = close_series[prior_mask]
    if prior_closes.empty:
        # Edge case: first trading day ever in data — use first window close
        # This is only triggered when baseline period is zero length
        start_close = window_closes.iloc[0]
        if start_close == 0:
            return 0.0
        return (end_close - start_close) / start_close
    else:
        prior_close = prior_closes.iloc[-1]
        if prior_close == 0:
            return 0.0
        return (end_close - prior_close) / prior_close


def _compute_volume_ratio(
    volume_series: pd.Series,
    event_date_ts: pd.Timestamp,
    baseline_mask: pd.Series,
) -> Optional[float]:
    """
    Volume ratio = event-day volume / mean(baseline volume).

    Returns None if event-day volume or baseline volume is unavailable/zero.
    """
    # Event-day volume
    event_vol_series = volume_series[volume_series.index == event_date_ts]
    if event_vol_series.empty or pd.isna(event_vol_series.iloc[0]):
        return None
    event_vol = float(event_vol_series.iloc[0])
    if event_vol == 0:
        return None

    baseline_vols = volume_series[baseline_mask]
    baseline_vols = baseline_vols.dropna()
    if baseline_vols.empty:
        return None
    baseline_mean = float(baseline_vols.mean())
    if baseline_mean == 0:
        return None

    return round(event_vol / baseline_mean, 4)


def _compute_realized_volatility(
    close_series: pd.Series,
    baseline_mask: pd.Series,
    annualisation_factor: int,
) -> Optional[float]:
    """
    Realized volatility = annualised std-dev of daily log-returns over
    the baseline period.

    Formula
    -------
        vol = std(log(P_t / P_{t-1})) * sqrt(annualisation_factor)

    Returns None if fewer than 2 observations available.
    """
    baseline_closes = close_series[baseline_mask].dropna()
    if len(baseline_closes) < 2:
        return None

    log_returns = np.log(baseline_closes / baseline_closes.shift(1)).dropna()
    if len(log_returns) < 1:
        return None

    return round(float(log_returns.std() * np.sqrt(annualisation_factor)), 6)


# ---------------------------------------------------------------------------
# Main fetcher class
# ---------------------------------------------------------------------------


class MarketContextFetcher:
    """
    Fetches market data from yfinance and computes MarketContext fields.

    Usage
    -----
    >>> config = MarketContextConfig(event_window_days=1, baseline_days=20)
    >>> fetcher = MarketContextFetcher(config)
    >>> result = fetcher.fetch(ticker="AAPL", event_timestamp=ts, sector="technology")
    >>> signal.market_context = result.market_context

    Notes on leakage prevention
    ---------------------------
    * The download window is anchored at or before the event timestamp.
    * No future columns (e.g., 1_DAY_RETURN) are read.
    * The close price used as the event-window *end* is the anchor-date
      close (last observable price before/at the event), not any
      subsequent price.
    * The baseline is computed entirely from pre-event data.
    """

    def __init__(self, config: Optional[MarketContextConfig] = None) -> None:
        self.config = config or MarketContextConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch(
        self,
        ticker: str,
        event_timestamp: datetime,
        sector: Optional[str] = None,
    ) -> MarketContextResult:
        """
        Calculate market context for a given ticker and event timestamp.

        Parameters
        ----------
        ticker : str
            Yahoo Finance ticker for the company (e.g. "AAPL").
            Must not be empty.  Do not substitute a different ticker if
            resolution fails — raise TickerResolutionError instead.
        event_timestamp : datetime
            UTC (or tz-aware) timestamp of the event.
        sector : str, optional
            Company sector name used to look up the sector ETF benchmark.
            Case-insensitive.  If None or unmapped, sector_movement is None.

        Returns
        -------
        MarketContextResult
            Contains the populated MarketContext plus audit metadata.

        Raises
        ------
        TickerResolutionError
            Empty ticker, or yfinance returns no data for the ticker.
        NoTradingSessionError
            The event date falls entirely outside any available trading session.
        InsufficientHistoryError
            Fewer baseline days than min_baseline_days are available.
        MarketDataError
            Any other retrieval / calculation failure.
        """
        if not ticker or not ticker.strip():
            raise TickerResolutionError(
                "ticker must be a non-empty string — do not silently substitute "
                "a different company when entity resolution fails."
            )

        cfg = self.config
        event_date = _to_utc_date(event_timestamp)
        fetch_warnings: List[str] = []

        # ------------------------------------------------------------------
        # 1. Determine download range
        #    We need baseline_days + event_window_days trading days ending at
        #    event_date.  We over-fetch by 2× to account for weekends/holidays.
        # ------------------------------------------------------------------
        total_days_needed = cfg.baseline_days + cfg.event_window_days
        # Calendar buffer: assume at most ~35% non-trading (weekends + holidays)
        calendar_buffer = int(total_days_needed * 2.0) + 30
        download_start = event_date - timedelta(days=calendar_buffer)
        download_end = event_date  # inclusive (we're not fetching future data)

        # ------------------------------------------------------------------
        # 2. Download stock OHLCV
        # ------------------------------------------------------------------
        df = _fetch_ohlcv(ticker, download_start, download_end)
        close = df["Close"]

        # ------------------------------------------------------------------
        # 3. Locate anchor date (last trading day ≤ event_date)
        # ------------------------------------------------------------------
        anchor_ts = _locate_anchor_date(df, event_date)
        anchor_date = anchor_ts.date()

        # ------------------------------------------------------------------
        # 4. Identify event window trading days
        #    [event_window_start_ts, anchor_ts] — must contain
        #    exactly event_window_days trading days.
        # ------------------------------------------------------------------
        all_trading_days = df.index[df.index <= anchor_ts]
        if len(all_trading_days) < cfg.event_window_days:
            raise InsufficientHistoryError(
                f"Only {len(all_trading_days)} trading day(s) available on or "
                f"before {anchor_date}; need at least {cfg.event_window_days} "
                f"for the event window."
            )
        event_window_ts = all_trading_days[-cfg.event_window_days :]
        event_window_start_ts = event_window_ts[0]
        event_window_end_ts = event_window_ts[-1]  # == anchor_ts

        # ------------------------------------------------------------------
        # 5. Identify baseline trading days
        #    baseline_days trading days immediately before event_window_start
        # ------------------------------------------------------------------
        pre_event_days = df.index[df.index < event_window_start_ts]
        if len(pre_event_days) < cfg.min_baseline_days:
            raise InsufficientHistoryError(
                f"Only {len(pre_event_days)} pre-event trading day(s) available "
                f"before {event_window_start_ts.date()}; minimum required is "
                f"{cfg.min_baseline_days}. The ticker may have limited history."
            )
        baseline_ts = pre_event_days[-cfg.baseline_days :]
        baseline_start_ts = baseline_ts[0]
        baseline_end_ts = baseline_ts[-1]
        baseline_mask = (df.index >= baseline_start_ts) & (
            df.index <= baseline_end_ts
        )

        # ------------------------------------------------------------------
        # 6. Compute stock event-window return
        # ------------------------------------------------------------------
        stock_window_return = _compute_window_return(
            close, event_window_start_ts, event_window_end_ts
        )

        # ------------------------------------------------------------------
        # 7. Download broad-market index data
        # ------------------------------------------------------------------
        index_return: Optional[float] = None
        try:
            idx_df = _fetch_ohlcv(cfg.index_ticker, download_start, download_end)
            index_return = round(
                _compute_window_return(
                    idx_df["Close"],
                    event_window_start_ts,
                    event_window_end_ts,
                ),
                6,
            )
        except (TickerResolutionError, BenchmarkUnavailableError) as exc:
            fetch_warnings.append(
                f"Broad-market benchmark '{cfg.index_ticker}' unavailable: {exc}"
            )
        except Exception as exc:
            fetch_warnings.append(
                f"Could not compute index return for '{cfg.index_ticker}': {exc}"
            )

        # ------------------------------------------------------------------
        # 8. Compute abnormal return  (stock − index)
        # ------------------------------------------------------------------
        abnormal_return: Optional[float]
        if index_return is not None:
            abnormal_return = round(stock_window_return - index_return, 6)
        else:
            # No benchmark available; report raw stock return as abnormal
            abnormal_return = round(stock_window_return, 6)
            fetch_warnings.append(
                "No benchmark available; abnormal_return set to raw stock return."
            )

        # ------------------------------------------------------------------
        # 9. Volume ratio
        # ------------------------------------------------------------------
        volume_col = "Volume" if "Volume" in df.columns else None
        volume_ratio: Optional[float] = None
        if volume_col:
            volume_ratio = _compute_volume_ratio(
                df[volume_col], anchor_ts, baseline_mask
            )
            if volume_ratio is None:
                fetch_warnings.append(
                    "Volume data missing or zero for the event day or baseline; "
                    "volume_ratio set to None."
                )
        else:
            fetch_warnings.append("Volume column absent in OHLCV data.")

        # ------------------------------------------------------------------
        # 10. Realized volatility (annualised, over baseline period)
        # ------------------------------------------------------------------
        volatility: Optional[float] = None
        # Use at most volatility_window days from the baseline
        vol_window_ts = pre_event_days[-cfg.volatility_window :]
        vol_mask = (df.index >= vol_window_ts[0]) & (
            df.index <= vol_window_ts[-1]
        )
        volatility = _compute_realized_volatility(
            close, vol_mask, cfg.volatility_annualisation_factor
        )
        if volatility is None:
            fetch_warnings.append(
                "Insufficient baseline closes to compute realized volatility."
            )

        # ------------------------------------------------------------------
        # 11. Sector benchmark movement
        # ------------------------------------------------------------------
        sector_ticker: Optional[str] = None
        sector_movement: Optional[float] = None
        if sector:
            sector_key = sector.strip().lower()
            sector_ticker = cfg.sector_etf_map.get(sector_key)
            if sector_ticker is None:
                fetch_warnings.append(
                    f"Sector '{sector}' not found in sector_etf_map; "
                    f"sector_movement will be None."
                )
            else:
                try:
                    sec_df = _fetch_ohlcv(
                        sector_ticker, download_start, download_end
                    )
                    sector_movement = round(
                        _compute_window_return(
                            sec_df["Close"],
                            event_window_start_ts,
                            event_window_end_ts,
                        ),
                        6,
                    )
                except (TickerResolutionError, MarketDataError) as exc:
                    fetch_warnings.append(
                        f"Sector ETF '{sector_ticker}' data unavailable: {exc}. "
                        f"sector_movement set to None."
                    )

        # ------------------------------------------------------------------
        # 12. Build metadata for audit trail
        # ------------------------------------------------------------------
        metadata: Dict[str, Any] = {
            "observation_window": {
                "event_window_start": event_window_start_ts.date().isoformat(),
                "event_window_end": event_window_end_ts.date().isoformat(),
                "event_window_days": cfg.event_window_days,
            },
            "baseline_window": {
                "baseline_start": baseline_start_ts.date().isoformat(),
                "baseline_end": baseline_end_ts.date().isoformat(),
                "baseline_days_requested": cfg.baseline_days,
                "baseline_days_actual": int(baseline_mask.sum()),
            },
            "stock_window_return_raw": round(stock_window_return, 6),
            "index_ticker": cfg.index_ticker,
            "sector_ticker": sector_ticker,
            "anchor_date": anchor_date.isoformat(),
            "provider": "yfinance",
            "warnings": fetch_warnings,
        }

        # ------------------------------------------------------------------
        # 13. Assemble MarketContext (compatible with risk_signal.MarketContext)
        # ------------------------------------------------------------------
        market_ctx = MarketContext(
            abnormal_return=abnormal_return,
            volume_ratio=volume_ratio,
            volatility=volatility,
            sector_movement=sector_movement,
            index_movement=index_return,
            metadata=metadata,
        )

        return MarketContextResult(
            market_context=market_ctx,
            ticker=ticker,
            event_timestamp=(
                event_timestamp
                if event_timestamp.tzinfo
                else event_timestamp.replace(tzinfo=timezone.utc)
            ),
            anchor_date=anchor_date,
            event_window_start=event_window_start_ts.date(),
            event_window_end=event_window_end_ts.date(),
            baseline_start=baseline_start_ts.date(),
            baseline_end=baseline_end_ts.date(),
            index_ticker=cfg.index_ticker,
            sector_ticker=sector_ticker,
            warnings=fetch_warnings,
        )
