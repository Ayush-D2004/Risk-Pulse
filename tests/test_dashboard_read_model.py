#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit Tests — Dashboard Read Model / API Contract
================================================
Validates JSON serialization, schema stability, view projections,
deterministic demo fixtures, no mutation, and exact metric copy.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from src.dashboard.demo import (
    DEMO_GENERATED_AT,
    EVENT_GEOPOLITICAL,
    EVENT_NO_EVENT,
    EVENT_TESLA_CREDIT_8,
    EVENT_TESLA_CREDIT_10,
    build_demo_catalog,
    demo_signals,
)
from src.dashboard.models import (
    DASHBOARD_SCHEMA_VERSION,
    EventStressOverviewResponse,
    PortfolioOverviewResponse,
    RiskAttributionResponse,
    ScenarioComparisonResponse,
)
from src.dashboard.serialization import parse_json, to_json, to_jsonable
from src.dashboard.service import DashboardReadService
from src.portfolio.comparison_models import AttributionMetrics
from src.portfolio.scenario_comparison import ScenarioComparisonEngine
from src.portfolio.synthetic_portfolio import (
    generate_synthetic_portfolio,
    summarize_portfolio,
)
from src.risk.risk_signal import EventType


ENVELOPE_KEYS = {
    "schema_version",
    "generated_at",
    "portfolio_id",
    "event_id",
    "scenario_a_id",
    "scenario_b_id",
    "data",
}

PORTFOLIO_DATA_KEYS = {
    "total_ead",
    "exposure_count",
    "obligor_count",
    "sector_distribution",
    "geography_distribution",
    "rating_distribution",
    "top_obligors",
    "concentration_indicators",
}

EVENT_DATA_KEYS = {
    "event_id",
    "entity",
    "event_type",
    "sentiment",
    "impact_score",
    "impact_tier",
    "shock_scope",
    "affected_ead",
    "affected_ead_pct",
    "incremental_el",
    "mtm_impact",
    "deterministic_rationale",
    "stress_applied",
}

ATTRIBUTION_DATA_KEYS = {
    "event_id",
    "by_sector",
    "by_geography",
    "by_asset_type",
    "by_exposure",
}

ATTRIBUTION_ROW_KEYS = {
    "dimension_value",
    "exposure_count",
    "ead",
    "ead_pct",
    "incremental_el",
    "incremental_el_pct",
    "mtm_impact",
    "mtm_contribution_pct",
}

EXPOSURE_ROW_KEYS = {
    "exposure_id",
    "obligor",
    "asset_type",
    "sector",
    "geography",
    "ead",
    "incremental_el",
    "mtm_impact",
    "is_affected",
}

COMPARISON_DATA_KEYS = {
    "scenario_a",
    "scenario_b",
    "deltas",
    "attribution_differences",
}

FORBIDDEN_LABELS = ("best", "worst", "good", "bad")


class TestDashboardReadModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build_demo_catalog()
        cls.service = cls.catalog.service
        cls.fixed = DEMO_GENERATED_AT

    def _overview(self, event_id: str) -> EventStressOverviewResponse:
        return self.service.event_stress_overview(
            self.catalog.by_event_id[event_id],
            self.catalog.signal_by_event_id[event_id],
            generated_at=self.fixed,
        )

    def _attribution(self, event_id: str) -> RiskAttributionResponse:
        return self.service.risk_attribution(
            self.catalog.by_event_id[event_id],
            generated_at=self.fixed,
        )

    def test_json_serialization_all_views(self):
        """Every dashboard response is valid JSON."""
        portfolio_resp = self.service.portfolio_overview(generated_at=self.fixed)
        event_resp = self._overview(EVENT_TESLA_CREDIT_10)
        attr_resp = self._attribution(EVENT_TESLA_CREDIT_10)
        cmp_resp = self.service.scenario_comparison(
            self.catalog.by_event_id[EVENT_TESLA_CREDIT_8],
            self.catalog.by_event_id[EVENT_TESLA_CREDIT_10],
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_8],
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10],
            generated_at=self.fixed,
        )
        for resp in (portfolio_resp, event_resp, attr_resp, cmp_resp):
            payload = to_json(resp)
            parsed = parse_json(payload)
            self.assertIsInstance(parsed, dict)
            json.dumps(to_jsonable(resp))
            self.assertEqual(payload, resp.model_dump_json())

    def test_schema_stability_envelope_and_views(self):
        """Envelope and data keys are closed and stable."""
        portfolio_resp = self.service.portfolio_overview(generated_at=self.fixed)
        p = to_jsonable(portfolio_resp)
        self.assertEqual(set(p.keys()), ENVELOPE_KEYS)
        self.assertEqual(set(p["data"].keys()), PORTFOLIO_DATA_KEYS)
        self.assertEqual(p["schema_version"], DASHBOARD_SCHEMA_VERSION)

        event_resp = to_jsonable(self._overview(EVENT_TESLA_CREDIT_10))
        self.assertEqual(set(event_resp.keys()), ENVELOPE_KEYS)
        self.assertEqual(set(event_resp["data"].keys()), EVENT_DATA_KEYS)

        attr_resp = to_jsonable(self._attribution(EVENT_TESLA_CREDIT_10))
        self.assertEqual(set(attr_resp.keys()), ENVELOPE_KEYS)
        self.assertEqual(set(attr_resp["data"].keys()), ATTRIBUTION_DATA_KEYS)
        self.assertEqual(set(attr_resp["data"]["by_sector"][0].keys()), ATTRIBUTION_ROW_KEYS)
        self.assertEqual(set(attr_resp["data"]["by_exposure"][0].keys()), EXPOSURE_ROW_KEYS)

        cmp_resp = to_jsonable(
            self.service.scenario_comparison(
                self.catalog.by_event_id[EVENT_TESLA_CREDIT_8],
                self.catalog.by_event_id[EVENT_TESLA_CREDIT_10],
                self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_8],
                self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10],
                generated_at=self.fixed,
            )
        )
        self.assertEqual(set(cmp_resp.keys()), ENVELOPE_KEYS)
        self.assertEqual(set(cmp_resp["data"].keys()), COMPARISON_DATA_KEYS)
        self.assertEqual(
            set(cmp_resp["data"]["deltas"].keys()),
            {
                "affected_ead_difference",
                "incremental_el_difference",
                "absolute_mtm_difference",
            },
        )
        blob = json.dumps(cmp_resp).lower()
        for label in FORBIDDEN_LABELS:
            self.assertNotIn(f'"{label}"', blob)

        for model in (
            PortfolioOverviewResponse,
            EventStressOverviewResponse,
            RiskAttributionResponse,
            ScenarioComparisonResponse,
        ):
            self.assertEqual(model.model_config.get("extra"), "forbid")
            self.assertTrue(model.model_config.get("frozen"))

    def test_portfolio_overview(self):
        """Portfolio overview copies summary totals and distributions."""
        portfolio = generate_synthetic_portfolio()
        summary = summarize_portfolio(portfolio)
        resp = DashboardReadService(portfolio).portfolio_overview(generated_at=self.fixed)

        self.assertEqual(resp.portfolio_id, portfolio.portfolio_id)
        self.assertIsNone(resp.event_id)
        self.assertEqual(resp.data.total_ead, summary.total_ead)
        self.assertEqual(resp.data.total_ead, portfolio.total_ead)
        self.assertEqual(resp.data.exposure_count, summary.exposure_count)
        self.assertEqual(
            resp.data.obligor_count,
            len({e.obligor for e in portfolio.exposures}),
        )
        self.assertEqual(
            {s.name: s.ead for s in resp.data.sector_distribution},
            summary.by_sector,
        )
        self.assertEqual(
            {s.name: s.ead for s in resp.data.geography_distribution},
            summary.by_geography,
        )
        self.assertEqual(
            {s.name: s.ead for s in resp.data.rating_distribution},
            summary.by_rating,
        )
        self.assertEqual(
            resp.data.concentration_indicators,
            summary.concentration_flags,
        )
        self.assertEqual(resp.data.top_obligors[0].obligor, summary.top_obligors[0]["obligor"])
        self.assertEqual(resp.data.top_obligors[0].ead, summary.top_obligors[0]["ead"])
        self.assertEqual(resp.data.top_obligors[0].pct, summary.top_obligors[0]["pct"])

    def test_scenario_overview_tesla_credit_10(self):
        """Event stress overview copies engine fields and signal sentiment."""
        result = self.catalog.by_event_id[EVENT_TESLA_CREDIT_10]
        signal = self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10]
        resp = self._overview(EVENT_TESLA_CREDIT_10)

        self.assertEqual(resp.event_id, EVENT_TESLA_CREDIT_10)
        self.assertEqual(resp.data.event_id, result.event_id)
        self.assertEqual(resp.data.entity, result.affected_entity)
        self.assertEqual(resp.data.event_type, result.event_type)
        self.assertEqual(resp.data.sentiment, signal.sentiment_score)
        self.assertEqual(resp.data.impact_score, result.impact_score)
        self.assertEqual(resp.data.impact_tier, result.impact_tier)
        self.assertEqual(resp.data.shock_scope, result.shock_scenario.shock_scope)
        self.assertEqual(resp.data.affected_ead, result.affected_ead)
        self.assertEqual(resp.data.affected_ead_pct, result.affected_ead_pct)
        self.assertEqual(resp.data.incremental_el, result.incremental_expected_loss)
        self.assertEqual(resp.data.mtm_impact, result.total_mtm_impact)
        self.assertEqual(resp.data.deterministic_rationale, result.rationale)
        self.assertTrue(resp.data.stress_applied)
        self.assertGreater(resp.data.incremental_el, Decimal("0"))

    def test_attribution_response(self):
        """Attribution rows copy ScenarioComparisonEngine metrics exactly."""
        result = self.catalog.by_event_id[EVENT_TESLA_CREDIT_10]
        engine_attr = ScenarioComparisonEngine().extract_attribution(result)
        resp = self._attribution(EVENT_TESLA_CREDIT_10)

        self.assertEqual(resp.data.event_id, engine_attr.event_id)
        self._assert_attr_lists_equal(resp.data.by_sector, engine_attr.by_sector)
        self._assert_attr_lists_equal(resp.data.by_geography, engine_attr.by_geography)
        self._assert_attr_lists_equal(resp.data.by_asset_type, engine_attr.by_asset_type)

        affected = [e for e in result.stressed_exposures if e.is_affected]
        self.assertEqual(len(resp.data.by_exposure), len(affected))
        by_id = {e.exposure_id: e for e in affected}
        for row in resp.data.by_exposure:
            src = by_id[row.exposure_id]
            self.assertEqual(row.ead, src.ead)
            self.assertEqual(row.incremental_el, src.incremental_expected_loss)
            self.assertEqual(row.mtm_impact, src.mtm_impact)
            self.assertTrue(row.is_affected)

    def _assert_attr_lists_equal(self, dto_rows, engine_rows: list[AttributionMetrics]):
        self.assertEqual(len(dto_rows), len(engine_rows))
        for dto, src in zip(dto_rows, engine_rows):
            self.assertEqual(dto.dimension_value, src.dimension_value)
            self.assertEqual(dto.exposure_count, src.exposure_count)
            self.assertEqual(dto.ead, src.ead)
            self.assertEqual(dto.ead_pct, src.ead_pct)
            self.assertEqual(dto.incremental_el, src.incremental_expected_loss)
            self.assertEqual(dto.incremental_el_pct, src.incremental_expected_loss_pct)
            self.assertEqual(dto.mtm_impact, src.mtm_impact)
            self.assertEqual(dto.mtm_contribution_pct, src.mtm_impact_pct)

    def test_scenario_comparison_response(self):
        """Comparison copies B−A deltas from ScenarioComparisonEngine."""
        res_a = self.catalog.by_event_id[EVENT_TESLA_CREDIT_8]
        res_b = self.catalog.by_event_id[EVENT_TESLA_CREDIT_10]
        pair = ScenarioComparisonEngine().compare(res_a, res_b)
        resp = self.service.scenario_comparison(
            res_a,
            res_b,
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_8],
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10],
            generated_at=self.fixed,
        )

        self.assertEqual(resp.scenario_a_id, EVENT_TESLA_CREDIT_8)
        self.assertEqual(resp.scenario_b_id, EVENT_TESLA_CREDIT_10)
        self.assertEqual(
            resp.data.deltas.affected_ead_difference,
            pair.deltas.delta_affected_ead,
        )
        self.assertEqual(
            resp.data.deltas.incremental_el_difference,
            pair.deltas.delta_incremental_expected_loss,
        )
        self.assertEqual(
            resp.data.deltas.absolute_mtm_difference,
            pair.deltas.delta_absolute_mtm,
        )
        self.assertEqual(resp.data.scenario_a.impact_score, 8.0)
        self.assertEqual(resp.data.scenario_b.impact_score, 10.0)
        self.assertGreater(resp.data.deltas.incremental_el_difference, Decimal("0"))
        self.assertTrue(resp.data.attribution_differences.by_sector)
        self.assertTrue(resp.data.attribution_differences.by_asset_type)

    def test_no_event_response(self):
        """NO_EVENT dashboard views carry zero stress metrics from the engine."""
        result = self.catalog.by_event_id[EVENT_NO_EVENT]
        resp = self._overview(EVENT_NO_EVENT)
        attr = self._attribution(EVENT_NO_EVENT)

        self.assertEqual(result.event_type, EventType.NO_EVENT.value)
        self.assertFalse(result.stress_applied)
        self.assertEqual(resp.data.affected_ead, Decimal("0"))
        self.assertEqual(resp.data.incremental_el, Decimal("0"))
        self.assertEqual(resp.data.mtm_impact, Decimal("0"))
        self.assertEqual(resp.data.affected_ead, result.affected_ead)
        self.assertEqual(resp.data.incremental_el, result.incremental_expected_loss)
        self.assertFalse(resp.data.stress_applied)
        self.assertIn("No stress applied", resp.data.deterministic_rationale)
        self.assertEqual(attr.data.by_sector, [])
        self.assertEqual(attr.data.by_exposure, [])

    def test_deterministic_demo_fixtures(self):
        """Demo catalog is deterministic: same IDs, same financials, no RNG."""
        a = build_demo_catalog()
        b = build_demo_catalog()
        self.assertEqual([s.event_id for s in a.signals], [s.event_id for s in b.signals])
        self.assertEqual(
            {EVENT_TESLA_CREDIT_10, EVENT_TESLA_CREDIT_8, EVENT_GEOPOLITICAL, EVENT_NO_EVENT},
            set(a.by_event_id),
        )
        for event_id in a.by_event_id:
            self.assertEqual(
                a.by_event_id[event_id].model_dump_json(),
                b.by_event_id[event_id].model_dump_json(),
            )
        tesla_10 = a.by_event_id[EVENT_TESLA_CREDIT_10]
        tesla_8 = a.by_event_id[EVENT_TESLA_CREDIT_8]
        geo = a.by_event_id[EVENT_GEOPOLITICAL]
        none = a.by_event_id[EVENT_NO_EVENT]
        self.assertEqual(tesla_10.impact_score, 10.0)
        self.assertEqual(tesla_10.affected_entity, "Tesla")
        self.assertEqual(tesla_10.event_type, EventType.CREDIT_EVENT.value)
        self.assertEqual(tesla_8.impact_score, 8.0)
        self.assertEqual(geo.event_type, EventType.GEOPOLITICAL.value)
        self.assertEqual(none.event_type, EventType.NO_EVENT.value)
        self.assertEqual(demo_signals()[0].event_id, EVENT_TESLA_CREDIT_10)
        json_a = to_json(a.service.portfolio_overview(generated_at=self.fixed))
        json_b = to_json(b.service.portfolio_overview(generated_at=self.fixed))
        self.assertEqual(json_a, json_b)

    def test_generated_at_does_not_change_financials(self):
        """generated_at is metadata only."""
        t1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        r1 = self._overview(EVENT_TESLA_CREDIT_10)
        r2 = self.service.event_stress_overview(
            self.catalog.by_event_id[EVENT_TESLA_CREDIT_10],
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10],
            generated_at=t2,
        )
        r1_alt = self.service.event_stress_overview(
            self.catalog.by_event_id[EVENT_TESLA_CREDIT_10],
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10],
            generated_at=t1,
        )
        self.assertEqual(r1.data, r2.data)
        self.assertEqual(r1_alt.data, r2.data)
        self.assertNotEqual(r1_alt.generated_at, r2.generated_at)

    def test_no_mutation_of_source_results(self):
        """Building dashboard views must not mutate engine results."""
        result = self.catalog.by_event_id[EVENT_TESLA_CREDIT_10]
        before = result.model_dump_json()
        _ = self._overview(EVENT_TESLA_CREDIT_10)
        _ = self._attribution(EVENT_TESLA_CREDIT_10)
        _ = self.service.scenario_comparison(
            result,
            self.catalog.by_event_id[EVENT_NO_EVENT],
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10],
            self.catalog.signal_by_event_id[EVENT_NO_EVENT],
            generated_at=self.fixed,
        )
        self.assertEqual(result.model_dump_json(), before)
        self.assertTrue(result.model_config.get("frozen"))

    def test_exact_preservation_of_financial_metrics(self):
        """Dashboard decimals are the same Decimal objects' values as the engine."""
        for event_id in (
            EVENT_TESLA_CREDIT_10,
            EVENT_TESLA_CREDIT_8,
            EVENT_GEOPOLITICAL,
            EVENT_NO_EVENT,
        ):
            result = self.catalog.by_event_id[event_id]
            overview = self._overview(event_id).data
            self.assertIsInstance(overview.affected_ead, Decimal)
            self.assertIsInstance(overview.incremental_el, Decimal)
            self.assertIsInstance(overview.mtm_impact, Decimal)
            self.assertEqual(overview.affected_ead, result.affected_ead)
            self.assertEqual(overview.affected_ead_pct, result.affected_ead_pct)
            self.assertEqual(overview.incremental_el, result.incremental_expected_loss)
            self.assertEqual(overview.mtm_impact, result.total_mtm_impact)

            attr = self._attribution(event_id)
            engine_attr = ScenarioComparisonEngine().extract_attribution(result)
            for dto, src in zip(attr.data.by_sector, engine_attr.by_sector):
                self.assertEqual(dto.ead, src.ead)
                self.assertEqual(dto.incremental_el, src.incremental_expected_loss)
                self.assertEqual(dto.mtm_impact, src.mtm_impact)
                self.assertEqual(dto.ead_pct, src.ead_pct)
                self.assertEqual(dto.incremental_el_pct, src.incremental_expected_loss_pct)
                self.assertEqual(dto.mtm_contribution_pct, src.mtm_impact_pct)

        res_a = self.catalog.by_event_id[EVENT_TESLA_CREDIT_8]
        res_b = self.catalog.by_event_id[EVENT_TESLA_CREDIT_10]
        pair = ScenarioComparisonEngine().compare(res_a, res_b)
        cmp = self.service.scenario_comparison(
            res_a,
            res_b,
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_8],
            self.catalog.signal_by_event_id[EVENT_TESLA_CREDIT_10],
            generated_at=self.fixed,
        )
        self.assertEqual(cmp.data.deltas.affected_ead_difference, pair.deltas.delta_affected_ead)
        self.assertEqual(
            cmp.data.deltas.incremental_el_difference,
            pair.deltas.delta_incremental_expected_loss,
        )
        self.assertEqual(cmp.data.deltas.absolute_mtm_difference, pair.deltas.delta_absolute_mtm)


if __name__ == "__main__":
    unittest.main()
