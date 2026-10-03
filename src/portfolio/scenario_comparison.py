#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scenario Comparison & Risk Attribution Engine
=============================================
Calculates descriptive risk attribution and deterministic comparisons
between multiple StressScenarioResults.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List

from src.portfolio.orchestration_models import StressScenarioResult
from src.portfolio.stress_models import StressedExposure
from src.portfolio.comparison_models import (
    AttributionMetrics,
    BatchComparisonMatrix,
    RiskAttribution,
    ScenarioComparisonDelta,
    ScenarioComparisonPair,
)


class ScenarioComparisonEngine:
    """
    Deterministic Scenario Comparison and Risk Attribution engine.
    """

    def _compute_attribution_metrics(
        self, 
        base_aggregations: List, 
        total_affected_ead: Decimal, 
        total_incremental_el: Decimal, 
        total_mtm_impact: Decimal
    ) -> List[AttributionMetrics]:
        """Convert Orchestration AggregationMetrics to AttributionMetrics with percentages."""
        metrics_list = []
        
        for agg in base_aggregations:
            # EAD % (relative to affected EAD)
            if total_affected_ead > 0:
                ead_pct = float(agg.ead / total_affected_ead)
            else:
                ead_pct = 0.0
                
            # Incremental EL %
            if total_incremental_el > 0:
                el_pct = float(agg.incremental_expected_loss / total_incremental_el)
            else:
                el_pct = 0.0
                
            # MTM Impact %
            if total_mtm_impact != 0:
                mtm_pct = float(agg.mtm_impact / total_mtm_impact)
            else:
                mtm_pct = 0.0

            metrics_list.append(AttributionMetrics(
                dimension_value=agg.dimension_value,
                exposure_count=agg.exposure_count,
                ead=agg.ead,
                ead_pct=ead_pct,
                incremental_expected_loss=agg.incremental_expected_loss,
                incremental_expected_loss_pct=el_pct,
                mtm_impact=agg.mtm_impact,
                mtm_impact_pct=mtm_pct
            ))
            
        return metrics_list

    def extract_attribution(self, result: StressScenarioResult) -> RiskAttribution:
        """
        Calculate risk attribution metrics for a single scenario result.
        Returns detailed attribution by sector, geography, asset type, and top exposures.
        """
        affected = result.affected_ead
        inc_el = result.incremental_expected_loss
        mtm = result.total_mtm_impact
        
        attr_sector = self._compute_attribution_metrics(result.by_sector, affected, inc_el, mtm)
        attr_geography = self._compute_attribution_metrics(result.by_geography, affected, inc_el, mtm)
        attr_asset = self._compute_attribution_metrics(result.by_asset_type, affected, inc_el, mtm)
        
        # Filter only affected exposures for top extraction
        affected_exposures = [e for e in result.stressed_exposures if e.is_affected]
        
        # Extract top exposures deterministically (breaking ties with exposure_id)
        # Top by EAD
        top_by_ead = sorted(
            affected_exposures, 
            key=lambda e: (-float(e.ead), e.exposure_id)
        )[:5]
        
        # Top by Incremental EL
        top_by_el = sorted(
            affected_exposures, 
            key=lambda e: (-float(e.incremental_expected_loss), e.exposure_id)
        )[:5]
        
        # Top by Absolute MTM Impact (since MTM is typically negative for losses)
        top_by_mtm = sorted(
            affected_exposures, 
            key=lambda e: (-float(abs(e.mtm_impact)), e.exposure_id)
        )[:5]

        return RiskAttribution(
            event_id=result.event_id,
            by_sector=attr_sector,
            by_geography=attr_geography,
            by_asset_type=attr_asset,
            top_exposures_by_ead=top_by_ead,
            top_exposures_by_el=top_by_el,
            top_exposures_by_mtm=top_by_mtm,
        )

    def compare(self, result_a: StressScenarioResult, result_b: StressScenarioResult) -> ScenarioComparisonPair:
        """
        Compare two scenarios deterministically.
        Calculates mathematical deltas (B - A).
        """
        delta_ead = result_b.affected_ead - result_a.affected_ead
        delta_el = result_b.incremental_expected_loss - result_a.incremental_expected_loss
        
        # Absolute MTM comparison (magnitude of the shock, regardless of sign)
        abs_mtm_a = abs(result_a.total_mtm_impact)
        abs_mtm_b = abs(result_b.total_mtm_impact)
        delta_abs_mtm = abs_mtm_b - abs_mtm_a

        deltas = ScenarioComparisonDelta(
            delta_affected_ead=delta_ead,
            delta_incremental_expected_loss=delta_el,
            delta_absolute_mtm=delta_abs_mtm
        )

        return ScenarioComparisonPair(
            scenario_a_id=result_a.event_id,
            scenario_b_id=result_b.event_id,
            scenario_a=result_a,
            scenario_b=result_b,
            deltas=deltas
        )

    def compare_batch(self, results: List[StressScenarioResult]) -> BatchComparisonMatrix:
        """
        Build a deterministic comparison matrix/table for an ordered batch of scenarios.
        """
        scenario_ids = [r.event_id for r in results]
        attributions = [self.extract_attribution(r) for r in results]
        
        return BatchComparisonMatrix(
            scenario_ids=scenario_ids,
            scenarios=results,
            attributions=attributions
        )
