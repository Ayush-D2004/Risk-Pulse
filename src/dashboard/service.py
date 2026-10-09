#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard read service
======================
Projects existing Module B results into dashboard DTOs.

Financial values are copied from:
  - Portfolio / PortfolioSummary
  - StressScenarioResult
  - RiskAttribution / AttributionMetrics (via ScenarioComparisonEngine)
  - ScenarioComparisonDelta (via ScenarioComparisonEngine)

This module does not compute EL, PD, LGD, MTM, affected EAD, or
attribution percentages. Sentiment is copied from the originating
RiskSignal (not from the frozen stress engines).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from src.dashboard.models import (
    DASHBOARD_SCHEMA_VERSION,
    AttributionDeltaRow,
    AttributionDifferences,
    AttributionRow,
    ComparisonDeltas,
    EadSlice,
    EventStressOverviewData,
    EventStressOverviewResponse,
    ExposureAttributionRow,
    ObligorConcentrationRow,
    PortfolioOverviewData,
    PortfolioOverviewResponse,
    RiskAttributionData,
    RiskAttributionResponse,
    ScenarioComparisonData,
    ScenarioComparisonResponse,
)
from src.portfolio.comparison_models import AttributionMetrics
from src.portfolio.models import Portfolio
from src.portfolio.orchestration_models import StressScenarioResult
from src.portfolio.scenario_comparison import ScenarioComparisonEngine
from src.portfolio.synthetic_portfolio import summarize_portfolio
from src.risk.risk_signal import RiskSignal


def _utc_now(generated_at: Optional[datetime]) -> datetime:
    if generated_at is not None:
        return generated_at
    return datetime.now(timezone.utc)


def _ead_slices(mapping: Dict[str, Decimal]) -> List[EadSlice]:
    return [EadSlice(name=name, ead=ead) for name, ead in sorted(mapping.items())]


def _copy_attribution_row(metric: AttributionMetrics) -> AttributionRow:
    return AttributionRow(
        dimension_value=metric.dimension_value,
        exposure_count=metric.exposure_count,
        ead=metric.ead,
        ead_pct=metric.ead_pct,
        incremental_el=metric.incremental_expected_loss,
        incremental_el_pct=metric.incremental_expected_loss_pct,
        mtm_impact=metric.mtm_impact,
        mtm_contribution_pct=metric.mtm_impact_pct,
    )


def _copy_exposure_rows(result: StressScenarioResult) -> List[ExposureAttributionRow]:
    rows: List[ExposureAttributionRow] = []
    for exp in result.stressed_exposures:
        if not exp.is_affected:
            continue
        rows.append(
            ExposureAttributionRow(
                exposure_id=exp.exposure_id,
                obligor=exp.obligor,
                asset_type=exp.asset_type,
                sector=exp.sector,
                geography=exp.geography,
                ead=exp.ead,
                incremental_el=exp.incremental_expected_loss,
                mtm_impact=exp.mtm_impact,
                is_affected=exp.is_affected,
            )
        )
    rows.sort(key=lambda r: (-float(r.ead), r.exposure_id))
    return rows


def _shock_scope(result: StressScenarioResult) -> Optional[str]:
    if result.shock_scenario is None:
        return None
    return result.shock_scenario.shock_scope


def project_event_overview(
    result: StressScenarioResult,
    signal: RiskSignal,
    provenance: Optional[str] = None,
) -> EventStressOverviewData:
    """Copy event-level metrics from a completed stress result + originating signal."""
    return EventStressOverviewData(
        event_id=result.event_id,
        entity=result.affected_entity,
        event_type=result.event_type,
        sentiment=signal.sentiment_score,
        impact_score=result.impact_score,
        impact_tier=result.impact_tier,
        shock_scope=_shock_scope(result),
        affected_ead=result.affected_ead,
        affected_ead_pct=result.affected_ead_pct,
        incremental_el=result.incremental_expected_loss,
        mtm_impact=result.total_mtm_impact,
        deterministic_rationale=result.rationale,
        stress_applied=result.stress_applied,
        provenance=provenance or (
            "HISTORICAL_REPLAY" if signal.source == "REAL PIPELINE EVENT" else "SYNTHETIC_FIXTURE"
        ),
    )


def _zero_metric(dimension_value: str) -> AttributionMetrics:
    """Placeholder zeros when a dimension exists on only one side of a comparison."""
    return AttributionMetrics(
        dimension_value=dimension_value,
        exposure_count=0,
        ead=Decimal("0"),
        ead_pct=0.0,
        incremental_expected_loss=Decimal("0"),
        incremental_expected_loss_pct=0.0,
        mtm_impact=Decimal("0"),
        mtm_impact_pct=0.0,
    )


def _diff_attribution_lists(
    list_a: Sequence[AttributionMetrics],
    list_b: Sequence[AttributionMetrics],
) -> List[AttributionDeltaRow]:
    by_a = {m.dimension_value: m for m in list_a}
    by_b = {m.dimension_value: m for m in list_b}
    keys = sorted(set(by_a) | set(by_b))
    rows: List[AttributionDeltaRow] = []
    for key in keys:
        a = by_a.get(key) or _zero_metric(key)
        b = by_b.get(key) or _zero_metric(key)
        rows.append(
            AttributionDeltaRow(
                dimension_value=key,
                ead_difference=b.ead - a.ead,
                incremental_el_difference=(
                    b.incremental_expected_loss - a.incremental_expected_loss
                ),
                mtm_impact_difference=b.mtm_impact - a.mtm_impact,
                ead_pct_difference=b.ead_pct - a.ead_pct,
                incremental_el_pct_difference=(
                    b.incremental_expected_loss_pct - a.incremental_expected_loss_pct
                ),
                mtm_contribution_pct_difference=b.mtm_impact_pct - a.mtm_impact_pct,
            )
        )
    return rows


class DashboardReadService:
    """Read-only application layer for dashboard JSON responses."""

    def __init__(
        self,
        portfolio: Portfolio,
        comparison_engine: Optional[ScenarioComparisonEngine] = None,
    ) -> None:
        self._portfolio = portfolio
        self._comparison = comparison_engine or ScenarioComparisonEngine()

    def portfolio_overview(
        self,
        generated_at: Optional[datetime] = None,
    ) -> PortfolioOverviewResponse:
        summary = summarize_portfolio(self._portfolio)
        obligors = {exp.obligor for exp in self._portfolio.exposures}
        data = PortfolioOverviewData(
            total_ead=summary.total_ead,
            exposure_count=summary.exposure_count,
            obligor_count=len(obligors),
            sector_distribution=_ead_slices(summary.by_sector),
            geography_distribution=_ead_slices(summary.by_geography),
            rating_distribution=_ead_slices(summary.by_rating),
            top_obligors=[
                ObligorConcentrationRow(
                    obligor=row["obligor"],
                    ead=row["ead"],
                    pct=row["pct"],
                )
                for row in summary.top_obligors
            ],
            concentration_indicators=list(summary.concentration_flags),
        )
        return PortfolioOverviewResponse(
            schema_version=DASHBOARD_SCHEMA_VERSION,
            generated_at=_utc_now(generated_at),
            portfolio_id=self._portfolio.portfolio_id,
            event_id=None,
            scenario_a_id=None,
            scenario_b_id=None,
            data=data,
        )

    def event_stress_overview(
        self,
        result: StressScenarioResult,
        signal: RiskSignal,
        generated_at: Optional[datetime] = None,
        provenance: Optional[str] = None,
    ) -> EventStressOverviewResponse:
        data = project_event_overview(result, signal, provenance)
        return EventStressOverviewResponse(
            schema_version=DASHBOARD_SCHEMA_VERSION,
            generated_at=_utc_now(generated_at),
            portfolio_id=self._portfolio.portfolio_id,
            event_id=result.event_id,
            scenario_a_id=None,
            scenario_b_id=None,
            data=data,
        )

    def risk_attribution(
        self,
        result: StressScenarioResult,
        generated_at: Optional[datetime] = None,
    ) -> RiskAttributionResponse:
        attribution = self._comparison.extract_attribution(result)
        data = RiskAttributionData(
            event_id=attribution.event_id,
            by_sector=[_copy_attribution_row(m) for m in attribution.by_sector],
            by_geography=[_copy_attribution_row(m) for m in attribution.by_geography],
            by_asset_type=[_copy_attribution_row(m) for m in attribution.by_asset_type],
            by_exposure=_copy_exposure_rows(result),
        )
        return RiskAttributionResponse(
            schema_version=DASHBOARD_SCHEMA_VERSION,
            generated_at=_utc_now(generated_at),
            portfolio_id=self._portfolio.portfolio_id,
            event_id=result.event_id,
            scenario_a_id=None,
            scenario_b_id=None,
            data=data,
        )

    def scenario_comparison(
        self,
        result_a: StressScenarioResult,
        result_b: StressScenarioResult,
        signal_a: RiskSignal,
        signal_b: RiskSignal,
        generated_at: Optional[datetime] = None,
    ) -> ScenarioComparisonResponse:
        pair = self._comparison.compare(result_a, result_b)
        attr_a = self._comparison.extract_attribution(result_a)
        attr_b = self._comparison.extract_attribution(result_b)
        data = ScenarioComparisonData(
            scenario_a=project_event_overview(result_a, signal_a, getattr(signal_a, "_provenance", None)),
            scenario_b=project_event_overview(result_b, signal_b, getattr(signal_b, "_provenance", None)),
            deltas=ComparisonDeltas(
                affected_ead_difference=pair.deltas.delta_affected_ead,
                incremental_el_difference=pair.deltas.delta_incremental_expected_loss,
                absolute_mtm_difference=pair.deltas.delta_absolute_mtm,
            ),
            attribution_differences=AttributionDifferences(
                by_sector=_diff_attribution_lists(attr_a.by_sector, attr_b.by_sector),
                by_geography=_diff_attribution_lists(
                    attr_a.by_geography, attr_b.by_geography
                ),
                by_asset_type=_diff_attribution_lists(
                    attr_a.by_asset_type, attr_b.by_asset_type
                ),
            ),
        )
        return ScenarioComparisonResponse(
            schema_version=DASHBOARD_SCHEMA_VERSION,
            generated_at=_utc_now(generated_at),
            portfolio_id=self._portfolio.portfolio_id,
            event_id=None,
            scenario_a_id=pair.scenario_a_id,
            scenario_b_id=pair.scenario_b_id,
            data=data,
        )
