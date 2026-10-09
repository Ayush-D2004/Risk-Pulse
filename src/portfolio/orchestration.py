#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stress Scenario Orchestration
=============================
Connects the Risk Engine (RiskSignal) to the Portfolio Stress models.
Consumes: RiskSignal, Portfolio
Pipeline: RiskSignal -> ShockMapper -> ShockScenario -> StressEngine -> StressScenarioResult
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from src.risk.risk_signal import EventType, RiskSignal
from src.portfolio.models import Portfolio
from src.portfolio.shock_mapper import ShockMapper
from src.portfolio.shock_models import ShockScope
from src.portfolio.stress_engine import StressEngine
from src.portfolio.stress_models import StressedExposure, StressedPortfolio
from src.portfolio.orchestration_models import AggregationMetrics, StressScenarioResult


class StressScenarioEngine:
    """
    Deterministic Orchestration Layer for Portfolio Stress Testing.
    """

    def __init__(self, portfolio: Portfolio, shock_mapper: Optional[ShockMapper] = None) -> None:
        """
        Initialize the orchestration engine.
        Args:
            portfolio: The canonical portfolio to run stress against.
            shock_mapper: Optional custom ShockMapper, defaults to standard.
        """
        self._portfolio = portfolio
        self._mapper = shock_mapper or ShockMapper()
        self._stress_engine = StressEngine(portfolio)

    def _format_money(self, val: Decimal) -> str:
        """Format decimal as concise string (e.g. $2.295M)."""
        v = float(val)
        abs_v = abs(v)
        if abs_v >= 1_000_000_000:
            return f"${v / 1_000_000_000:,.3f}B".replace("$-", "-$")
        elif abs_v >= 1_000_000:
            return f"${v / 1_000_000:,.3f}M".replace("$-", "-$")
        elif abs_v >= 1_000:
            return f"${v / 1_000:,.3f}K".replace("$-", "-$")
        return f"${v:,.2f}".replace("$-", "-$")

    def _build_explanation(self, result: StressScenarioResult, signal: Optional[RiskSignal] = None) -> str:
        """Deterministically assemble a human-readable explanation."""
        if result.error:
            return f"Validation Error: {result.error}"

        shock_scope = result.shock_scenario.shock_scope if result.shock_scenario else 'NONE'

        lines = []
        if signal and signal.evidence and signal.evidence.text:
            cleaned_text = signal.evidence.text.strip()
            if cleaned_text and cleaned_text not in ("Deterministic dashboard demo fixture", "Test", "Mock text"):
                lines.append(cleaned_text)

        lines.extend([
            f"{result.event_type} affecting {result.affected_entity}.",
            f"Impact score: {result.impact_score:.1f} ({result.impact_tier}).",
            f"Shock scope: {shock_scope}.",
            f"Affected EAD: {self._format_money(result.affected_ead)} ({result.affected_ead_pct * 100:.2f}% of portfolio).",
            f"Incremental expected loss: {self._format_money(result.incremental_expected_loss)}.",
            f"MTM impact: {self._format_money(result.total_mtm_impact)}."
        ])
        if shock_scope == "ENTITY" and result.affected_exposure_count == 0:
            lines.append(f"Unheld Counterparty: {result.affected_entity} is not currently held in the wholesale credit portfolio. Direct single-name credit loss is $0.00.")

        return " ".join(lines)

    def _aggregate(
        self,
        dimension_extractor,
        exposures: List[StressedExposure],
        total_portfolio_ead: Decimal,
    ) -> List[AggregationMetrics]:
        """Group and sum affected exposures by a specific dimension."""
        groups: Dict[str, Dict[str, Any]] = {}
        
        for exp in exposures:
            if not exp.is_affected:
                continue
                
            dim = dimension_extractor(exp)
            if dim not in groups:
                groups[dim] = {
                    "count": 0,
                    "ead": Decimal("0"),
                    "inc_el": Decimal("0"),
                    "mtm": Decimal("0")
                }
                
            groups[dim]["count"] += 1
            groups[dim]["ead"] += exp.ead
            groups[dim]["inc_el"] += exp.incremental_expected_loss
            groups[dim]["mtm"] += exp.mtm_impact
            
        metrics = []
        for dim, aggs in groups.items():
            pct = float(aggs["ead"] / total_portfolio_ead) if total_portfolio_ead > 0 else 0.0
            metrics.append(AggregationMetrics(
                dimension_value=dim,
                exposure_count=aggs["count"],
                ead=aggs["ead"],
                ead_pct_of_portfolio=pct,
                incremental_expected_loss=aggs["inc_el"],
                mtm_impact=aggs["mtm"]
            ))
            
        # Sort deterministically by EAD descending, then by name
        metrics.sort(key=lambda m: (-float(m.ead), m.dimension_value))
        return metrics

    def _create_error_result(self, signal: RiskSignal, error_msg: str) -> StressScenarioResult:
        """Create a standard result representing a validation failure."""
        return StressScenarioResult(
            event_id=signal.event_id,
            affected_entity=signal.entity,
            event_type=signal.event_type or "UNKNOWN",
            impact_score=signal.impact_score if signal.impact_score is not None else 1.0,
            impact_tier="Minimal Impact",
            stress_applied=False,
            shock_scenario=None,
            affected_exposure_count=0,
            affected_ead=Decimal("0"),
            affected_ead_pct=0.0,
            base_expected_loss=Decimal("0"),
            stressed_expected_loss=Decimal("0"),
            incremental_expected_loss=Decimal("0"),
            total_mtm_impact=Decimal("0"),
            by_sector=[],
            by_geography=[],
            by_asset_type=[],
            rationale=f"Validation Error: {error_msg}",
            stressed_exposures=[],
            error=error_msg,
        )

    def run_signal(self, signal: RiskSignal) -> StressScenarioResult:
        """
        Process a single RiskSignal through the orchestration pipeline.
        """
        # --- Validation ---
        if not signal.event_id:
            return self._create_error_result(signal, "Missing event_id")
        
        if not signal.event_type:
            return self._create_error_result(signal, "Missing event type")
            
        impact = signal.impact_score
        if impact is None:
            return self._create_error_result(signal, "Missing impact score")
            
        if impact < 1.0 or impact > 10.0:
            return self._create_error_result(signal, f"Invalid impact score {impact}")

        # --- Mapping ---
        try:
            scenario = self._mapper.map(signal)
        except Exception as e:
            return self._create_error_result(signal, f"Mapping failed: {str(e)}")

        # --- NO_EVENT Short-circuit ---
        if scenario.shock_scope == ShockScope.NONE.value or scenario.event_type == EventType.NO_EVENT.value:
            res = StressScenarioResult(
                event_id=signal.event_id,
                affected_entity=signal.entity,
                event_type=scenario.event_type,
                impact_score=impact,
                impact_tier=scenario.impact_tier,
                stress_applied=False,
                shock_scenario=scenario,
                affected_exposure_count=0,
                affected_ead=Decimal("0"),
                affected_ead_pct=0.0,
                base_expected_loss=Decimal("0"),
                stressed_expected_loss=Decimal("0"),
                incremental_expected_loss=Decimal("0"),
                total_mtm_impact=Decimal("0"),
                by_sector=[],
                by_geography=[],
                by_asset_type=[],
                rationale="No stress applied for event type: NO_EVENT.",
                stressed_exposures=[],
                error=None,
            )
            return res

        # --- Execution ---
        stress_result = self._stress_engine.run_stress(scenario)
        
        # Determine if stress was meaningfully applied
        stress_applied = stress_result.affected_exposure_count > 0

        # --- Aggregation ---
        total_ead = self._portfolio.total_ead
        by_sector = self._aggregate(lambda e: e.sector, stress_result.stressed_exposures, total_ead)
        by_geography = self._aggregate(lambda e: e.geography, stress_result.stressed_exposures, total_ead)
        by_asset = self._aggregate(lambda e: e.asset_type, stress_result.stressed_exposures, total_ead)

        # --- Construction ---
        result_pre = StressScenarioResult(
            event_id=signal.event_id,
            affected_entity=signal.entity,
            event_type=scenario.event_type,
            impact_score=impact,
            impact_tier=scenario.impact_tier,
            stress_applied=stress_applied,
            shock_scenario=scenario,
            affected_exposure_count=stress_result.affected_exposure_count,
            affected_ead=stress_result.affected_ead,
            affected_ead_pct=stress_result.affected_ead_pct,
            base_expected_loss=stress_result.base_expected_loss,
            stressed_expected_loss=stress_result.stressed_expected_loss,
            incremental_expected_loss=stress_result.incremental_expected_loss,
            total_mtm_impact=stress_result.total_mtm_impact,
            by_sector=by_sector,
            by_geography=by_geography,
            by_asset_type=by_asset,
            rationale="",  # Placeholder, built next
            stressed_exposures=stress_result.stressed_exposures,
            error=None,
        )
        
        # Generate and inject explanation
        expl = self._build_explanation(result_pre, signal=signal)
        
        # Reconstruct with rationale
        d = result_pre.model_dump()
        d["rationale"] = expl
        final_result = StressScenarioResult(**d)
        
        return final_result

    def run_batch(self, signals: List[RiskSignal]) -> List[StressScenarioResult]:
        """
        Process multiple signals sequentially and deterministically.
        """
        results = []
        for sig in signals:
            try:
                res = self.run_signal(sig)
                results.append(res)
            except Exception as e:
                # One failing signal must not corrupt others.
                err_res = self._create_error_result(sig, f"Unhandled exception: {str(e)}")
                results.append(err_res)
        return results
