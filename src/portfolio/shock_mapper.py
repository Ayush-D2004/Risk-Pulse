#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Event → Shock Mapper
======================
Deterministic rule-based mapping from a scored RiskSignal to a ShockScenario.

Design principles
-----------------
1. **Read-only**: Does NOT modify the input RiskSignal.
2. **Pure output**: Produces an immutable ShockScenario; does NOT touch portfolio.
3. **Deterministic**: Identical input → identical output.  No randomness.
4. **Monotonic**: Higher impact_score → equal or greater absolute shock magnitude
   for the same event type.
5. **Bounded**: All shock parameters are clamped within explicit maximum bounds.
6. **Auditable**: Every scenario carries a rule_id and human-readable rationale.

Severity normalization
----------------------
    severity_factor = (impact_score − 1) / 9

    impact 1.0  → factor 0.000  (no shock beyond base minimum)
    impact 5.5  → factor 0.500
    impact 10.0 → factor 1.000  (maximum base shock)

For each event type, the base shock parameters define the *maximum* shock at
severity_factor = 1.0.  The actual shock is:

    shock = base_shock × severity_factor

Then clamped within [0, MAX_*] bounds.

Scope rules
-----------
Scope is determined by event type, NOT by impact score.

| Event Type              | Default Scope  |
|-------------------------|----------------|
| Credit Event            | ENTITY         |
| Geopolitical            | GEOGRAPHY      |
| Macroeconomic           | BROAD_MARKET   |
| Merger & Acquisition    | ENTITY         |
| Regulatory / Legal      | ENTITY         |
| Corporate / Earnings    | ENTITY         |
| Product / Technology    | ENTITY         |
| Commodity / Supply Chain| SECTOR         |
| Market / Liquidity      | BROAD_MARKET   |
| Other / Unclear         | ENTITY         |
| NO_EVENT                | NONE           |
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.risk.risk_signal import EventType, RiskSignal
from src.portfolio.shock_models import (
    ASSET_SHOCK_APPLICABILITY,
    MAX_BOND_SHOCK_NEG,
    MAX_BOND_SHOCK_POS,
    MAX_EQUITY_SHOCK_NEG,
    MAX_EQUITY_SHOCK_POS,
    MAX_LGD_DELTA,
    MAX_PD_DELTA,
    ShockScenario,
    ShockScope,
)


# ---------------------------------------------------------------------------
# Base shock parameter table (at severity_factor = 1.0)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _BaseShockRule:
    """Defines base shock magnitudes and scope for one EventType."""
    rule_id: str
    event_type: str
    scope: ShockScope
    pd_delta: float          # max absolute PD increase
    lgd_delta: float         # max absolute LGD increase
    bond_price_shock: float  # max bond price decline (negative)
    equity_price_shock: float  # max equity price decline (negative)
    description: str


# The deterministic rule table — one row per EventType value.
_RULE_TABLE: Dict[str, _BaseShockRule] = {
    # ── Credit-default-style events ──
    EventType.CREDIT_EVENT.value: _BaseShockRule(
        rule_id="RULE-CREDIT-01",
        event_type=EventType.CREDIT_EVENT.value,
        scope=ShockScope.ENTITY,
        pd_delta=0.15,
        lgd_delta=0.15,
        bond_price_shock=-0.20,
        equity_price_shock=-0.40,
        description="Credit default / downgrade — severe single-name shock",
    ),

    # ── Broad / systemic events ──
    EventType.GEOPOLITICAL.value: _BaseShockRule(
        rule_id="RULE-GEO-01",
        event_type=EventType.GEOPOLITICAL.value,
        scope=ShockScope.GEOGRAPHY,
        pd_delta=0.05,
        lgd_delta=0.05,
        bond_price_shock=-0.10,
        equity_price_shock=-0.15,
        description="Geopolitical risk — geography-wide credit/market stress",
    ),
    EventType.MACROECONOMIC.value: _BaseShockRule(
        rule_id="RULE-MACRO-01",
        event_type=EventType.MACROECONOMIC.value,
        scope=ShockScope.BROAD_MARKET,
        pd_delta=0.04,
        lgd_delta=0.03,
        bond_price_shock=-0.08,
        equity_price_shock=-0.12,
        description="Macroeconomic shift — broad-market rate/growth shock",
    ),

    # ── Company-specific events ──
    EventType.MERGER_ACQUISITION.value: _BaseShockRule(
        rule_id="RULE-MA-01",
        event_type=EventType.MERGER_ACQUISITION.value,
        scope=ShockScope.ENTITY,
        pd_delta=0.02,
        lgd_delta=0.01,
        bond_price_shock=-0.05,
        equity_price_shock=-0.20,
        description="M&A event — acquirer leverage/credit risk, equity re-pricing",
    ),
    EventType.REGULATORY_LEGAL.value: _BaseShockRule(
        rule_id="RULE-REG-01",
        event_type=EventType.REGULATORY_LEGAL.value,
        scope=ShockScope.ENTITY,
        pd_delta=0.04,
        lgd_delta=0.03,
        bond_price_shock=-0.08,
        equity_price_shock=-0.15,
        description="Regulatory / legal action — fine, sanction, or structural remedy",
    ),
    EventType.CORPORATE_EARNINGS.value: _BaseShockRule(
        rule_id="RULE-EARN-01",
        event_type=EventType.CORPORATE_EARNINGS.value,
        scope=ShockScope.ENTITY,
        pd_delta=0.03,
        lgd_delta=0.02,
        bond_price_shock=-0.06,
        equity_price_shock=-0.15,
        description="Corporate / earnings miss — entity credit deterioration",
    ),
    EventType.PRODUCT_TECHNOLOGY.value: _BaseShockRule(
        rule_id="RULE-PROD-01",
        event_type=EventType.PRODUCT_TECHNOLOGY.value,
        scope=ShockScope.ENTITY,
        pd_delta=0.01,
        lgd_delta=0.005,
        bond_price_shock=-0.03,
        equity_price_shock=-0.10,
        description="Product / technology event — minor credit, moderate equity impact",
    ),

    # ── Market-price / liquidity events ──
    EventType.COMMODITY_SUPPLY_CHAIN.value: _BaseShockRule(
        rule_id="RULE-COMM-01",
        event_type=EventType.COMMODITY_SUPPLY_CHAIN.value,
        scope=ShockScope.SECTOR,
        pd_delta=0.04,
        lgd_delta=0.04,
        bond_price_shock=-0.07,
        equity_price_shock=-0.10,
        description="Commodity / supply-chain disruption — sector-wide stress",
    ),
    EventType.MARKET_LIQUIDITY.value: _BaseShockRule(
        rule_id="RULE-MLIQ-01",
        event_type=EventType.MARKET_LIQUIDITY.value,
        scope=ShockScope.BROAD_MARKET,
        pd_delta=0.03,
        lgd_delta=0.02,
        bond_price_shock=-0.10,
        equity_price_shock=-0.12,
        description="Market / liquidity event — broad-market spread widening",
    ),

    # ── Catch-all ──
    EventType.OTHER_UNCLEAR.value: _BaseShockRule(
        rule_id="RULE-OTHER-01",
        event_type=EventType.OTHER_UNCLEAR.value,
        scope=ShockScope.ENTITY,
        pd_delta=0.01,
        lgd_delta=0.005,
        bond_price_shock=-0.02,
        equity_price_shock=-0.05,
        description="Unclear / other event — minimal conservative shock",
    ),

    # ── No event ──
    EventType.NO_EVENT.value: _BaseShockRule(
        rule_id="RULE-NONE-01",
        event_type=EventType.NO_EVENT.value,
        scope=ShockScope.NONE,
        pd_delta=0.0,
        lgd_delta=0.0,
        bond_price_shock=0.0,
        equity_price_shock=0.0,
        description="No event — zero shock",
    ),
}


# ---------------------------------------------------------------------------
# Severity normalization
# ---------------------------------------------------------------------------

def compute_severity_factor(impact_score: float) -> float:
    """
    Normalize impact score [1, 10] to severity factor [0, 1].

    Formula: (impact_score − 1) / 9

    Monotonic and linear:
        1.0  → 0.000
        5.5  → 0.500
        10.0 → 1.000
    """
    if impact_score < 1.0 or impact_score > 10.0:
        raise ValueError(
            f"impact_score must be in [1.0, 10.0], got {impact_score}"
        )
    return round((impact_score - 1.0) / 9.0, 6)


# ---------------------------------------------------------------------------
# Impact tier (mirrors ImpactScorer._determine_tier — read-only reference)
# ---------------------------------------------------------------------------

def _determine_tier(score: float) -> str:
    """Classify impact score into the same tiers used by ImpactScorer."""
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


# ---------------------------------------------------------------------------
# Clamping helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi] and round to 6 decimal places."""
    return round(max(lo, min(hi, value)), 6)


# ---------------------------------------------------------------------------
# The Shock Mapper
# ---------------------------------------------------------------------------

class ShockMapper:
    """
    Deterministic Event → Shock Mapper.

    Converts a scored RiskSignal into a ShockScenario without modifying
    the signal or any portfolio state.

    Usage::

        mapper = ShockMapper()
        scenario = mapper.map(risk_signal)
    """

    def __init__(
        self,
        rule_table: Optional[Dict[str, _BaseShockRule]] = None,
    ) -> None:
        """
        Initialize the mapper.

        Args:
            rule_table: Optional override of the default rule table.
        """
        self._rules = dict(rule_table or _RULE_TABLE)
        # Normalized lookup for case-insensitive matching
        self._norm_rules: Dict[str, _BaseShockRule] = {
            k.strip().lower(): v for k, v in self._rules.items()
        }

    def _resolve_rule(self, event_type: str) -> _BaseShockRule:
        """Look up the rule for an event type, falling back to OTHER_UNCLEAR."""
        if event_type in self._rules:
            return self._rules[event_type]
        norm = event_type.strip().lower()
        if norm in self._norm_rules:
            return self._norm_rules[norm]
        return self._rules[EventType.OTHER_UNCLEAR.value]

    def _determine_applicable_assets(self, scope: ShockScope) -> List[str]:
        """
        Determine which asset classes a shock applies to, based on scope.

        All scopes (except NONE) can affect all asset types — the shock
        *magnitude* differs per-field and per-asset, but eligibility is
        universal for ENTITY/SECTOR/GEOGRAPHY/BROAD_MARKET/SYSTEMIC.
        """
        if scope == ShockScope.NONE:
            return []
        return list(ASSET_SHOCK_APPLICABILITY.keys())

    def map(self, signal: RiskSignal) -> ShockScenario:
        """
        Map a scored RiskSignal to a ShockScenario.

        The signal must already have impact_score populated (by ImpactScorer).
        If impact_score is None, it is treated as 1.0 (minimal).

        Args:
            signal: A RiskSignal (not modified).

        Returns:
            Immutable ShockScenario.

        Raises:
            ValueError: If impact_score is outside [1.0, 10.0].
        """
        # --- Extract inputs (read-only) ---
        impact = signal.impact_score if signal.impact_score is not None else 1.0

        if impact < 1.0 or impact > 10.0:
            raise ValueError(
                f"impact_score must be in [1.0, 10.0], got {impact}"
            )

        event_type_str = signal.event_type
        entity = signal.entity
        event_id = signal.event_id

        # --- Resolve rule ---
        rule = self._resolve_rule(event_type_str)

        # --- Severity factor ---
        severity = compute_severity_factor(impact)

        # --- Scale base shocks by severity, then clamp ---
        pd_delta = _clamp(rule.pd_delta * severity, 0.0, MAX_PD_DELTA)
        lgd_delta = _clamp(rule.lgd_delta * severity, 0.0, MAX_LGD_DELTA)
        bond_shock = _clamp(
            rule.bond_price_shock * severity,
            MAX_BOND_SHOCK_NEG,
            MAX_BOND_SHOCK_POS,
        )
        equity_shock = _clamp(
            rule.equity_price_shock * severity,
            MAX_EQUITY_SHOCK_NEG,
            MAX_EQUITY_SHOCK_POS,
        )

        # --- Impact tier ---
        tier = _determine_tier(impact)

        # --- Scope (from event type, not from impact score) ---
        scope = rule.scope

        # --- Applicable assets ---
        applicable = self._determine_applicable_assets(scope)

        # --- Sector / geography hints ---
        # These are contextual hints for the stress engine.
        # For ENTITY scope, we don't pre-populate sector/geography —
        # the stress engine resolves those from the exposure model.
        affected_sector: Optional[str] = None
        affected_geography: Optional[str] = None

        if scope == ShockScope.SECTOR:
            # Commodity/supply chain events implicitly target the entity's sector
            # The stress engine will resolve this from the exposure match
            affected_sector = None  # resolved downstream
        elif scope == ShockScope.GEOGRAPHY:
            affected_geography = None  # resolved downstream

        # --- Rationale ---
        rationale = (
            f"{rule.description}. "
            f"Impact {impact:.1f}/10 ({tier}) → severity factor {severity:.4f}. "
            f"Scope: {scope.value}. "
            f"Scaled shocks: ΔPD={pd_delta:.6f}, ΔLGD={lgd_delta:.6f}, "
            f"bond={bond_shock:.6f}, equity={equity_shock:.6f}."
        )

        return ShockScenario(
            event_id=event_id,
            event_type=event_type_str,
            impact_score=impact,
            impact_tier=tier,
            affected_entity=entity,
            shock_scope=scope.value,
            affected_sector=affected_sector,
            affected_geography=affected_geography,
            pd_delta=pd_delta,
            lgd_delta=lgd_delta,
            bond_price_shock=bond_shock,
            equity_price_shock=equity_shock,
            severity_factor=severity,
            applicable_assets=applicable,
            rule_id=rule.rule_id,
            rationale=rationale,
        )

    def map_batch(self, signals: List[RiskSignal]) -> List[ShockScenario]:
        """Map a list of RiskSignals to ShockScenarios."""
        return [self.map(s) for s in signals]

    @property
    def rule_table(self) -> Dict[str, _BaseShockRule]:
        """Read-only access to the active rule table."""
        return dict(self._rules)


# ---------------------------------------------------------------------------
# Public rule-table access for reports / validation
# ---------------------------------------------------------------------------

def get_default_rule_table() -> Dict[str, _BaseShockRule]:
    """Return a copy of the default rule table."""
    return dict(_RULE_TABLE)
