#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic Impact Scoring Engine v1
======================================
Calculates financial impact scores (1.0 to 10.0) and auditable explanations
for incoming RiskSignals based on event severity priors, confidence, credibility,
novelty, market context, and sentiment.

Key Design Decisions:
---------------------
1. Deterministic & Explainable: Rule and prior-based, avoiding black-box ML
   at this stage so every score is fully traceable for risk managers and auditors.
2. Sentiment is NOT the primary driver: Event type severity and materiality
   drive the baseline; sentiment acts only as a bounded modifier.
3. Materiality Gating:
   - NO_EVENT -> clamped to 1.0
   - NON_MATERIAL_FINANCIAL_CONTENT -> clamped to [1.0, 2.0]
   - MATERIAL_EVENT -> full [1.0, 10.0] calculation
4. Formula:
   Base Event Severity (0-1)
   x Event Confidence
   x Source Credibility
   x Novelty
   x Market Reaction Modifier
   x Sentiment Modifier
   -> Normalized & Scaled to [1.0, 10.0]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from src.risk.risk_signal import MarketContext, MaterialityLevel, RiskSignal


# ---------------------------------------------------------------------------
# Configurable Prior Severity Map
# ---------------------------------------------------------------------------

DEFAULT_EVENT_SEVERITY: Dict[str, float] = {
    "Credit Event": 1.00,
    "Geopolitical": 0.90,
    "Macroeconomic": 0.85,
    "Merger & Acquisition": 0.80,
    "Regulatory / Legal": 0.75,
    "Corporate / Earnings": 0.70,
    "Commodity / Supply Chain": 0.70,
    "Market / Liquidity": 0.65,
    "Product / Technology": 0.50,
    "Other / Unclear": 0.30,
}


@dataclass
class ImpactScoreResult:
    """Detailed breakdown of the deterministic impact scoring calculation."""
    impact_score: float
    impact_reason: str
    impact_tier: str
    raw_composite: float
    base_severity: float
    event_confidence: float
    source_credibility: float
    novelty: float
    sentiment_modifier: float
    market_modifier: float
    is_gated: bool
    gate_reason: Optional[str] = None
    confidence_modifier: float = 1.0
    novelty_modifier: float = 1.0
    component_breakdown: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "impact_score": self.impact_score,
            "impact_tier": self.impact_tier,
            "impact_reason": self.impact_reason,
            "is_gated": self.is_gated,
            "gate_reason": self.gate_reason,
            "components": {
                "base_severity": self.base_severity,
                "event_confidence": self.event_confidence,
                "confidence_modifier": self.confidence_modifier,
                "source_credibility": self.source_credibility,
                "novelty": self.novelty,
                "novelty_modifier": self.novelty_modifier,
                "sentiment_modifier": self.sentiment_modifier,
                "market_modifier": self.market_modifier,
                "raw_composite": self.raw_composite,
            },
        }


class ImpactScorer:
    """
    Deterministic Impact Scorer for financial risk signals.
    """

    def __init__(
        self,
        event_severity_map: Optional[Dict[str, float]] = None,
        default_severity: float = 0.25,
        normalization_factor: float = 1.20,
        negative_sentiment_weight: float = 0.25,
        positive_sentiment_weight: float = 0.10,
    ):
        """
        Initialize the impact scorer with configurable priors and weights.

        Args:
            event_severity_map: Dictionary mapping event types to base severity [0.0, 1.0].
            default_severity: Fallback severity for unmapped event categories.
            normalization_factor: Composite multiplier scaling factor mapping to the 1-10 range.
            negative_sentiment_weight: Downside risk amplification weight for negative sentiment.
            positive_sentiment_weight: Magnitude amplification weight for positive sentiment.
        """
        self.severity_map = dict(event_severity_map or DEFAULT_EVENT_SEVERITY)
        self.default_severity = default_severity
        self.normalization_factor = normalization_factor
        self.neg_sent_weight = negative_sentiment_weight
        self.pos_sent_weight = positive_sentiment_weight

        # Pre-build normalized lookup table for case-insensitive matching
        self._norm_severity_map = {
            k.strip().lower(): v for k, v in self.severity_map.items()
        }

    def get_base_severity(self, event_type: str) -> float:
        """Resolve base event severity using exact or normalized lookup."""
        if not event_type:
            return 0.0
        # Direct lookup
        if event_type in self.severity_map:
            return self.severity_map[event_type]
        # Normalized lookup
        norm_key = event_type.strip().lower()
        if norm_key in self._norm_severity_map:
            return self._norm_severity_map[norm_key]
        return self.default_severity

    def compute_sentiment_modifier(self, sentiment_score: float) -> float:
        """
        Calculate bounded sentiment modifier.
        Sentiment modifies impact magnitude but is NOT the primary driver:
        - Negative sentiment amplifies downside risk (e.g. +25% at -1.0).
        - Positive sentiment provides a modest magnitude adjustment (e.g. +10% at +1.0).
        - Neutral sentiment remains at baseline ~1.0.
        """
        if sentiment_score < 0:
            return 1.0 + self.neg_sent_weight * abs(sentiment_score)
        elif sentiment_score > 0:
            return 1.0 + self.pos_sent_weight * sentiment_score
        return 1.0

    def compute_market_modifier(self, market_context: Optional[MarketContext]) -> float:
        """
        Calculate market reaction modifier based on observed market variables.
        Returns 1.0 (neutral) if no market context is provided.
        Bounded between 0.70 and 1.30.
        """
        if market_context is None:
            return 1.0

        modifier = 1.0

        # Abnormal return shock
        if market_context.abnormal_return is not None:
            car_mag = abs(market_context.abnormal_return)
            if car_mag > 0.015:
                # Add up to +15% boost for significant price dislocation
                car_boost = min(0.15, (car_mag - 0.015) * 3.0)
                modifier += car_boost
            elif car_mag < 0.005:
                # Dampen for muted market reactions
                modifier -= 0.10

        # Elevated volume ratio
        if market_context.volume_ratio is not None:
            if market_context.volume_ratio > 1.5:
                vol_boost = min(0.10, (market_context.volume_ratio - 1.5) * 0.05)
                modifier += vol_boost
            elif market_context.volume_ratio < 1.0:
                modifier -= 0.05

        # Realized or implied volatility
        if market_context.volatility is not None:
            if market_context.volatility > 2.0:
                modifier += 0.05
            elif market_context.volatility < 1.0:
                modifier -= 0.05

        return round(min(1.30, max(0.70, modifier)), 4)

    def compute_confidence_modifier(self, event_confidence: float) -> float:
        """
        Calculate bounded confidence modifier.
        Confidence reflects classifier certainty rather than reducing event severity.
        Formula: 0.70 + 0.30 * event_confidence
        - 1.00 -> 1.000
        - 0.95 -> 0.985
        - 0.65 -> 0.895
        - 0.50 -> 0.850
        - 0.00 -> 0.700
        """
        conf = max(0.0, min(1.0, float(event_confidence)))
        return round(0.70 + 0.30 * conf, 4)

    def compute_novelty_modifier(self, novelty: float) -> float:
        """
        Calculate bounded novelty modifier.
        Novelty represents incremental information / urgency rather than erasing event severity.
        Formula: 0.75 + 0.25 * novelty
        - 1.00 -> 1.000
        - 0.50 -> 0.875
        - 0.20 -> 0.800
        - 0.00 -> 0.750
        """
        nov = max(0.0, min(1.0, float(novelty)))
        return round(0.75 + 0.25 * nov, 4)

    def _determine_tier(self, score: float) -> str:
        """Classify numerical impact score into auditable severity tiers."""
        if score >= 8.5:
            return "Critical Impact"
        elif score >= 7.0:
            return "High Impact"
        elif score >= 5.0:
            return "Moderate Impact"
        elif score >= 3.0:
            return "Low Impact"
        else:
            return "Minimal Impact"

    def _generate_explanation(
        self,
        impact_score: float,
        tier: str,
        materiality: str,
        event_type: str,
        base_severity: float,
        event_confidence: float,
        source_credibility: float,
        novelty: float,
        sentiment_score: float,
        market_modifier: float,
        is_gated: bool,
    ) -> str:
        """Construct a transparent, auditable explanation for the impact score."""
        mat_norm = materiality.strip().upper()

        # Case 1: Gated by NO_EVENT
        if mat_norm == MaterialityLevel.NO_EVENT.value:
            return "Gated: Classified as NO_EVENT. Minimal financial significance (impact: 1.0)."

        # Case 2: Gated by NON_MATERIAL_FINANCIAL_CONTENT
        if mat_norm == MaterialityLevel.NON_MATERIAL_FINANCIAL_CONTENT.value:
            return (
                f"Gated: Classified as non-material financial content; score constrained to 1.0–2.0 "
                f"(impact: {impact_score:.1f}). Event category '{event_type}' (base severity: {base_severity:.2f}, "
                f"confidence: {event_confidence:.2f}) does not meet corporate materiality thresholds."
            )

        # Case 3: MATERIAL_EVENT full calculation
        # Confidence qualitative tag
        if event_confidence >= 0.85:
            conf_str = f"high event confidence ({event_confidence:.2f})"
        elif event_confidence >= 0.60:
            conf_str = f"moderate event confidence ({event_confidence:.2f})"
        else:
            conf_str = f"weak event confidence ({event_confidence:.2f})"

        # Credibility qualitative tag
        if source_credibility >= 0.90:
            cred_str = f"strong source credibility ({source_credibility:.2f})"
        elif source_credibility >= 0.60:
            cred_str = f"moderate source credibility ({source_credibility:.2f})"
        else:
            cred_str = f"unverified source credibility ({source_credibility:.2f})"

        parts = [
            f"{tier} ({impact_score:.1f}/10) because this is a material {event_type} "
            f"(base severity: {base_severity:.2f}) with {conf_str} and {cred_str}."
        ]

        # Sentiment contribution
        if sentiment_score <= -0.4:
            parts.append(f"Downside risk amplified by negative sentiment ({sentiment_score:+.2f}).")
        elif sentiment_score >= 0.4:
            parts.append(f"Positive sentiment ({sentiment_score:+.2f}); impact driven by structural transaction/event size.")
        else:
            parts.append(f"Sentiment is neutral ({sentiment_score:+.2f}); impact driven primarily by event severity.")

        # Novelty dampening
        if novelty < 0.70:
            parts.append(f"Dampened by lower novelty ({novelty:.2f}) due to repeated/clustered coverage.")

        # Market confirmation
        if market_modifier > 1.05:
            parts.append(f"Confirmed by elevated market reaction and volatility (market modifier: {market_modifier:.2f}).")
        elif market_modifier < 0.95:
            parts.append("Dampened by muted price/volume reaction.")

        return " ".join(parts)

    def calculate(self, signal: RiskSignal) -> ImpactScoreResult:
        """
        Calculate impact score and explainable breakdown for a RiskSignal.

        Args:
            signal: An instantiated RiskSignal.

        Returns:
            ImpactScoreResult containing impact_score, reason, tier, and factors.
        """
        mat_norm = signal.materiality.strip().upper()
        base_sev = self.get_base_severity(signal.event_type)
        conf_mod = self.compute_confidence_modifier(signal.event_confidence)
        nov_mod = self.compute_novelty_modifier(signal.novelty)
        sent_mod = self.compute_sentiment_modifier(signal.sentiment_score)
        mkt_mod = self.compute_market_modifier(signal.market_context)

        # Raw composite product with bounded modifiers
        raw_composite = (
            base_sev
            * conf_mod
            * signal.source_credibility
            * nov_mod
            * sent_mod
            * mkt_mod
        )

        # -------------------------------------------------------------------
        # Materiality Gating
        # -------------------------------------------------------------------
        if mat_norm == MaterialityLevel.NO_EVENT.value:
            final_score = 1.0
            is_gated = True
            gate_reason = "NO_EVENT"
            tier = self._determine_tier(final_score)
            reason = self._generate_explanation(
                impact_score=final_score,
                tier=tier,
                materiality=signal.materiality,
                event_type=signal.event_type,
                base_severity=base_sev,
                event_confidence=signal.event_confidence,
                source_credibility=signal.source_credibility,
                novelty=signal.novelty,
                sentiment_score=signal.sentiment_score,
                market_modifier=mkt_mod,
                is_gated=True,
            )
            return ImpactScoreResult(
                impact_score=1.0,
                impact_reason=reason,
                impact_tier=tier,
                raw_composite=raw_composite,
                base_severity=base_sev,
                event_confidence=signal.event_confidence,
                source_credibility=signal.source_credibility,
                novelty=signal.novelty,
                sentiment_modifier=sent_mod,
                market_modifier=mkt_mod,
                is_gated=True,
                gate_reason=gate_reason,
                confidence_modifier=conf_mod,
                novelty_modifier=nov_mod,
                component_breakdown={
                    "base_severity": base_sev,
                    "event_confidence": signal.event_confidence,
                    "confidence_modifier": conf_mod,
                    "source_credibility": signal.source_credibility,
                    "novelty": signal.novelty,
                    "novelty_modifier": nov_mod,
                    "sentiment_modifier": sent_mod,
                    "market_modifier": mkt_mod,
                },
            )

        if mat_norm == MaterialityLevel.NON_MATERIAL_FINANCIAL_CONTENT.value:
            # Constrained to 1.0 - 2.0
            scaled_fraction = min(1.0, max(0.0, raw_composite / self.normalization_factor))
            final_score = round(1.0 + 1.0 * scaled_fraction, 2)
            is_gated = True
            gate_reason = "NON_MATERIAL_FINANCIAL_CONTENT"
            tier = self._determine_tier(final_score)
            reason = self._generate_explanation(
                impact_score=final_score,
                tier=tier,
                materiality=signal.materiality,
                event_type=signal.event_type,
                base_severity=base_sev,
                event_confidence=signal.event_confidence,
                source_credibility=signal.source_credibility,
                novelty=signal.novelty,
                sentiment_score=signal.sentiment_score,
                market_modifier=mkt_mod,
                is_gated=True,
            )
            return ImpactScoreResult(
                impact_score=final_score,
                impact_reason=reason,
                impact_tier=tier,
                raw_composite=raw_composite,
                base_severity=base_sev,
                event_confidence=signal.event_confidence,
                source_credibility=signal.source_credibility,
                novelty=signal.novelty,
                sentiment_modifier=sent_mod,
                market_modifier=mkt_mod,
                is_gated=True,
                gate_reason=gate_reason,
                confidence_modifier=conf_mod,
                novelty_modifier=nov_mod,
                component_breakdown={
                    "base_severity": base_sev,
                    "event_confidence": signal.event_confidence,
                    "confidence_modifier": conf_mod,
                    "source_credibility": signal.source_credibility,
                    "novelty": signal.novelty,
                    "novelty_modifier": nov_mod,
                    "sentiment_modifier": sent_mod,
                    "market_modifier": mkt_mod,
                },
            )

        # Full calculation for MATERIAL_EVENT (and any non-suppressed event)
        scaled_fraction = min(1.0, max(0.0, raw_composite / self.normalization_factor))
        final_score = round(1.0 + 9.0 * scaled_fraction, 2)
        # Ensure strict bounds [1.0, 10.0]
        final_score = max(1.0, min(10.0, final_score))
        tier = self._determine_tier(final_score)
        reason = self._generate_explanation(
            impact_score=final_score,
            tier=tier,
            materiality=signal.materiality,
            event_type=signal.event_type,
            base_severity=base_sev,
            event_confidence=signal.event_confidence,
            source_credibility=signal.source_credibility,
            novelty=signal.novelty,
            sentiment_score=signal.sentiment_score,
            market_modifier=mkt_mod,
            is_gated=False,
        )

        return ImpactScoreResult(
            impact_score=final_score,
            impact_reason=reason,
            impact_tier=tier,
            raw_composite=raw_composite,
            base_severity=base_sev,
            event_confidence=signal.event_confidence,
            source_credibility=signal.source_credibility,
            novelty=signal.novelty,
            sentiment_modifier=sent_mod,
            market_modifier=mkt_mod,
            is_gated=False,
            gate_reason=None,
            confidence_modifier=conf_mod,
            novelty_modifier=nov_mod,
            component_breakdown={
                "base_severity": base_sev,
                "event_confidence": signal.event_confidence,
                "confidence_modifier": conf_mod,
                "source_credibility": signal.source_credibility,
                "novelty": signal.novelty,
                "novelty_modifier": nov_mod,
                "sentiment_modifier": sent_mod,
                "market_modifier": mkt_mod,
            },
        )

    def score(self, signal: RiskSignal, in_place: bool = False) -> RiskSignal:
        """
        Evaluate impact score and reason, attaching them to the RiskSignal.

        Args:
            signal: Input RiskSignal.
            in_place: If True, mutates the passed signal; if False, returns a modified copy.

        Returns:
            RiskSignal with impact_score and impact_reason populated.
        """
        result = self.calculate(signal)
        if in_place:
            signal.impact_score = result.impact_score
            signal.impact_reason = result.impact_reason
            return signal

        data = signal.to_dict()
        data["impact_score"] = result.impact_score
        data["impact_reason"] = result.impact_reason
        return RiskSignal.from_dict(data)

    def score_batch(self, signals: List[RiskSignal], in_place: bool = False) -> List[RiskSignal]:
        """Score a list of RiskSignals."""
        return [self.score(sig, in_place=in_place) for sig in signals]

    def score_dataframe_row(
        self,
        event_type: str,
        materiality: str,
        event_confidence: float,
        sentiment_score: float,
        source_credibility: float = 1.0,
        novelty: float = 1.0,
        market_context: Optional[MarketContext] = None,
    ) -> Tuple[float, str, str]:
        """
        Direct scalar scoring helper for DataFrame rows or streaming feeds.

        Returns:
            (impact_score, impact_reason, impact_tier)
        """
        # Create a lightweight signal mock or evaluate directly
        mat_norm = (materiality or "").strip().upper()
        base_sev = self.get_base_severity(event_type)
        conf_mod = self.compute_confidence_modifier(event_confidence)
        nov_mod = self.compute_novelty_modifier(novelty)
        sent_mod = self.compute_sentiment_modifier(sentiment_score)
        mkt_mod = self.compute_market_modifier(market_context)

        raw_composite = (
            base_sev
            * conf_mod
            * float(source_credibility)
            * nov_mod
            * sent_mod
            * mkt_mod
        )

        if mat_norm == MaterialityLevel.NO_EVENT.value:
            final_score = 1.0
            tier = self._determine_tier(final_score)
            reason = self._generate_explanation(
                impact_score=final_score,
                tier=tier,
                materiality=materiality,
                event_type=event_type,
                base_severity=base_sev,
                event_confidence=event_confidence,
                source_credibility=source_credibility,
                novelty=novelty,
                sentiment_score=sentiment_score,
                market_modifier=mkt_mod,
                is_gated=True,
            )
            return final_score, reason, tier

        if mat_norm == MaterialityLevel.NON_MATERIAL_FINANCIAL_CONTENT.value:
            scaled_fraction = min(1.0, max(0.0, raw_composite / self.normalization_factor))
            final_score = round(1.0 + 1.0 * scaled_fraction, 2)
            tier = self._determine_tier(final_score)
            reason = self._generate_explanation(
                impact_score=final_score,
                tier=tier,
                materiality=materiality,
                event_type=event_type,
                base_severity=base_sev,
                event_confidence=event_confidence,
                source_credibility=source_credibility,
                novelty=novelty,
                sentiment_score=sentiment_score,
                market_modifier=mkt_mod,
                is_gated=True,
            )
            return final_score, reason, tier

        scaled_fraction = min(1.0, max(0.0, raw_composite / self.normalization_factor))
        final_score = round(1.0 + 9.0 * scaled_fraction, 2)
        final_score = max(1.0, min(10.0, final_score))
        tier = self._determine_tier(final_score)
        reason = self._generate_explanation(
            impact_score=final_score,
            tier=tier,
            materiality=materiality,
            event_type=event_type,
            base_severity=base_sev,
            event_confidence=event_confidence,
            source_credibility=source_credibility,
            novelty=novelty,
            sentiment_score=sentiment_score,
            market_modifier=mkt_mod,
            is_gated=False,
        )
        return final_score, reason, tier
