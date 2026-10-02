#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Market-Context → ImpactScorer Pipeline Connector
=================================================
Wires MarketContextFetcher into the ImpactScorer so a RiskSignal can be
enriched with live (or mocked) market data before scoring.

Design
------
* The connector is a thin orchestration layer.  It does NOT modify the
  ImpactScorer, MarketContextFetcher, or RiskSignal schemas.
* Market data is fetched once per signal and attached as
  signal.market_context before calling scorer.calculate().
* All market-data failures (missing ticker, API error, etc.) are
  handled gracefully: the scorer always receives a signal and produces
  a result.  A missing MarketContext simply means market_modifier = 1.0.
* The ticker must be provided explicitly — the connector never silently
  substitutes a different company.

Enrichment Modes
----------------
LIVE  – calls yfinance in real time (production path).
MOCK  – accepts a pre-built MarketContext (testing / offline path).
SKIP  – skips market enrichment entirely and scores the raw signal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from src.market.market_context import (
    MarketContextConfig,
    MarketContextFetcher,
    MarketContextResult,
    MarketDataError,
    TickerResolutionError,
)
from src.risk.impact_scorer import ImpactScoreResult, ImpactScorer
from src.risk.risk_signal import MarketContext, RiskSignal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enrichment mode
# ---------------------------------------------------------------------------


class EnrichmentMode(Enum):
    LIVE = auto()   # fetch from yfinance
    MOCK = auto()   # use pre-built MarketContext supplied by caller
    SKIP = auto()   # score without any market context


# ---------------------------------------------------------------------------
# Enriched scoring result
# ---------------------------------------------------------------------------


@dataclass
class EnrichedScoringResult:
    """
    Composite result from the pipeline connector.

    Attributes
    ----------
    signal : RiskSignal
        The original signal (unmodified).
    enriched_signal : RiskSignal
        Signal with market_context populated (or None if enrichment failed).
    impact_result : ImpactScoreResult
        Full scoring breakdown.
    market_result : Optional[MarketContextResult]
        Full market-context fetch result including audit metadata.
        None when enrichment mode is SKIP or enrichment failed.
    enrichment_mode : EnrichmentMode
        The mode used for this scoring run.
    enrichment_warnings : list[str]
        Non-fatal warnings from market-data retrieval.
    enrichment_error : Optional[str]
        Description of a non-fatal enrichment failure, if any.
    """

    signal: RiskSignal
    enriched_signal: RiskSignal
    impact_result: ImpactScoreResult
    market_result: Optional[MarketContextResult]
    enrichment_mode: EnrichmentMode
    enrichment_warnings: list[str] = field(default_factory=list)
    enrichment_error: Optional[str] = None

    @property
    def impact_score(self) -> float:
        return self.impact_result.impact_score

    @property
    def market_modifier(self) -> float:
        return self.impact_result.market_modifier

    def summary(self) -> str:
        """Single-line human-readable summary."""
        mode_tag = self.enrichment_mode.name
        mkt_tag = (
            f"CAR={self.enriched_signal.market_context.abnormal_return:+.3f} "
            f"Vol×={self.enriched_signal.market_context.volume_ratio}"
            if self.enriched_signal.market_context
            else "no market ctx"
        )
        return (
            f"[{self.signal.event_id}] {self.signal.entity} | "
            f"score={self.impact_score:.2f} ({self.impact_result.impact_tier}) | "
            f"mkt_mod={self.market_modifier:.4f} | {mkt_tag} | mode={mode_tag}"
        )


# ---------------------------------------------------------------------------
# Main connector class
# ---------------------------------------------------------------------------


class MarketEnrichedScorer:
    """
    Orchestrates MarketContextFetcher + ImpactScorer into a single call.

    Usage
    -----
    >>> scorer = MarketEnrichedScorer()

    # Live scoring (fetches from yfinance):
    >>> result = scorer.score_live(signal, ticker="AAPL", sector="technology")

    # Offline / test scoring (pre-built context):
    >>> ctx = MarketContext(abnormal_return=-0.06, volume_ratio=3.0)
    >>> result = scorer.score_with_context(signal, market_context=ctx)

    # Score raw signal without any market data:
    >>> result = scorer.score_raw(signal)
    """

    def __init__(
        self,
        market_config: Optional[MarketContextConfig] = None,
        scorer: Optional[ImpactScorer] = None,
    ) -> None:
        self._fetcher = MarketContextFetcher(market_config or MarketContextConfig())
        self._scorer = scorer or ImpactScorer()

    # ------------------------------------------------------------------
    # Public scoring entry points
    # ------------------------------------------------------------------

    def score_live(
        self,
        signal: RiskSignal,
        ticker: str,
        sector: Optional[str] = None,
        on_error: str = "warn",
    ) -> EnrichedScoringResult:
        """
        Fetch market context from yfinance, attach to signal, then score.

        Parameters
        ----------
        signal : RiskSignal
            Input signal (unmodified).
        ticker : str
            Yahoo Finance ticker. Must match the signal entity — never
            substituted automatically.
        sector : str, optional
            Sector name for sector-ETF benchmark (e.g. "technology").
        on_error : str
            "warn"  – log a warning and score without market context.
            "raise" – propagate the MarketDataError to the caller.

        Returns
        -------
        EnrichedScoringResult
        """
        market_result: Optional[MarketContextResult] = None
        enrichment_error: Optional[str] = None
        enrichment_warnings: list[str] = []

        try:
            market_result = self._fetcher.fetch(
                ticker=ticker,
                event_timestamp=signal.timestamp,
                sector=sector,
            )
            enrichment_warnings = market_result.warnings
        except TickerResolutionError as exc:
            msg = f"Ticker resolution failed for '{ticker}': {exc}"
            if on_error == "raise":
                raise
            logger.warning(msg)
            enrichment_error = msg
        except MarketDataError as exc:
            msg = f"Market data unavailable for '{ticker}': {exc}"
            if on_error == "raise":
                raise
            logger.warning(msg)
            enrichment_error = msg
        except Exception as exc:
            msg = f"Unexpected error fetching market data for '{ticker}': {exc}"
            if on_error == "raise":
                raise
            logger.exception(msg)
            enrichment_error = msg

        market_ctx = market_result.market_context if market_result else None
        return self._build_result(
            signal,
            market_ctx=market_ctx,
            market_result=market_result,
            mode=EnrichmentMode.LIVE,
            warnings=enrichment_warnings,
            error=enrichment_error,
        )

    def score_with_context(
        self,
        signal: RiskSignal,
        market_context: Optional[MarketContext],
    ) -> EnrichedScoringResult:
        """
        Score using a pre-built MarketContext (offline / test path).

        Parameters
        ----------
        signal : RiskSignal
            Input signal.
        market_context : MarketContext or None
            Pre-computed context.  If None, scores as if no market data.
        """
        return self._build_result(
            signal,
            market_ctx=market_context,
            market_result=None,
            mode=EnrichmentMode.MOCK,
        )

    def score_raw(self, signal: RiskSignal) -> EnrichedScoringResult:
        """Score the signal with no market enrichment (market_modifier = 1.0)."""
        return self._build_result(
            signal,
            market_ctx=None,
            market_result=None,
            mode=EnrichmentMode.SKIP,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_result(
        self,
        signal: RiskSignal,
        market_ctx: Optional[MarketContext],
        market_result: Optional[MarketContextResult],
        mode: EnrichmentMode,
        warnings: Optional[list[str]] = None,
        error: Optional[str] = None,
    ) -> EnrichedScoringResult:
        """Attach market_context to a copy of the signal and run the scorer."""
        sig_data = signal.to_dict()
        sig_data["market_context"] = (
            market_ctx.model_dump() if market_ctx is not None else None
        )
        enriched = RiskSignal.from_dict(sig_data)

        impact_result = self._scorer.calculate(enriched)

        return EnrichedScoringResult(
            signal=signal,
            enriched_signal=enriched,
            impact_result=impact_result,
            market_result=market_result,
            enrichment_mode=mode,
            enrichment_warnings=warnings or [],
            enrichment_error=error,
        )
