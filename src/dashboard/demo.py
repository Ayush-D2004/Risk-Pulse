#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic dashboard demo fixtures
=====================================
Runs the existing (frozen) orchestration pipeline once against the
synthetic portfolio. No random data.

Scenarios:
  - Tesla credit event, impact 10
  - Tesla credit event, impact 8
  - Geopolitical scenario
  - NO_EVENT
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from src.dashboard.service import DashboardReadService
from src.portfolio.orchestration import StressScenarioEngine
from src.portfolio.orchestration_models import StressScenarioResult
from src.portfolio.synthetic_portfolio import generate_synthetic_portfolio
from src.risk.risk_signal import Evidence, EventType, RiskSignal


DEMO_GENERATED_AT = datetime(2024, 6, 30, 12, 0, 0, tzinfo=timezone.utc)
DEMO_SIGNAL_TS = datetime(2024, 6, 30, 0, 0, 0, tzinfo=timezone.utc)

EVENT_TESLA_CREDIT_10 = "DEMO-TESLA-CREDIT-10"
EVENT_TESLA_CREDIT_8 = "DEMO-TESLA-CREDIT-8"
EVENT_GEOPOLITICAL = "DEMO-GEOPOLITICAL"
EVENT_NO_EVENT = "DEMO-NO-EVENT"


def _signal(
    event_id: str,
    event_type: str,
    impact_score: float,
    entity: str,
    sentiment_score: float,
) -> RiskSignal:
    return RiskSignal(
        event_id=event_id,
        entity=entity,
        source="demo",
        sentiment_score=sentiment_score,
        event_type=event_type,
        event_confidence=1.0,
        materiality="MATERIAL_EVENT" if event_type != EventType.NO_EVENT.value else "NO_EVENT",
        impact_score=impact_score,
        evidence=Evidence(text="Deterministic dashboard demo fixture"),
        timestamp=DEMO_SIGNAL_TS,
    )


def demo_signals() -> List[RiskSignal]:
    """Fixed RiskSignal set. Identical on every call."""
    signals = [
        _signal(
            EVENT_TESLA_CREDIT_10,
            EventType.CREDIT_EVENT.value,
            10.0,
            "Tesla",
            -0.95,
        ),
        _signal(
            EVENT_TESLA_CREDIT_8,
            EventType.CREDIT_EVENT.value,
            8.0,
            "Tesla",
            -0.85,
        ),
        _signal(
            EVENT_GEOPOLITICAL,
            EventType.GEOPOLITICAL.value,
            7.5,
            "China",
            -0.80,
        ),
        _signal(
            EVENT_NO_EVENT,
            EventType.NO_EVENT.value,
            1.0,
            "Apple",
            0.0,
        ),
        _signal(
            "DEMO-REGULATORY-APPLE",
            EventType.REGULATORY_LEGAL.value,
            7.5,
            "Apple",
            -0.95,
        ),
        _signal(
            "DEMO-MA-AMAZON",
            EventType.MERGER_ACQUISITION.value,
            8.2,
            "Amazon",
            0.60,
        ),
        _signal(
            "DEMO-COMMODITY-PETRO",
            EventType.COMMODITY_SUPPLY_CHAIN.value,
            6.8,
            "PetroGlobal",
            -0.45,
        ),
        _signal(
            "TEST-MARKET-DAMPENING",
            EventType.CREDIT_EVENT.value,
            6.5,  # Dampened from 9.5 due to market modifier
            "Tesla",
            -0.85,
        ),
        _signal(
            "TEST-NOVELTY-HIGH",
            EventType.GEOPOLITICAL.value,
            9.0,  # High impact due to novelty = 1.0
            "Germany",
            -0.80,
        ),
        _signal(
            "TEST-GUARDRAIL-BLOCKED",
            EventType.CREDIT_EVENT.value,
            1.5,  # Impact slashed because financial guardrail blocked it
            "MidCapCorp",
            -0.90,
        ),
    ]

    # Load real pipeline event
    import os
    try:
        from src.integration.selector import select_real_event
        from src.integration.adapter import CanonicalEventAdapter
        
        csv_path = os.path.join("data", "pipeline_output", "canonical_events.csv")
        if os.path.exists(csv_path):
            raw_event = select_real_event(csv_path)
            real_signal = CanonicalEventAdapter.from_row(raw_event)
            # Mark it clearly for the dashboard
            real_signal.source = "REAL PIPELINE EVENT"
            signals.append(real_signal)
    except Exception as e:
        print(f"Failed to load real event for dashboard demo: {e}")

    return signals


@dataclass(frozen=True)
class DashboardDemoCatalog:
    """Completed engine results plus dashboard read service for demos/tests."""

    portfolio_id: str
    signals: Tuple[RiskSignal, ...]
    results: Tuple[StressScenarioResult, ...]
    by_event_id: Dict[str, StressScenarioResult]
    signal_by_event_id: Dict[str, RiskSignal]
    service: DashboardReadService


def build_demo_catalog() -> DashboardDemoCatalog:
    """
    Produce the demo catalog by calling StressScenarioEngine once.
    All financial figures come from the frozen backend.
    """
    portfolio = generate_synthetic_portfolio()
    engine = StressScenarioEngine(portfolio)
    signals = demo_signals()
    results = engine.run_batch(signals)
    by_event = {r.event_id: r for r in results}
    by_signal = {s.event_id: s for s in signals}
    service = DashboardReadService(portfolio)
    return DashboardDemoCatalog(
        portfolio_id=portfolio.portfolio_id,
        signals=tuple(signals),
        results=tuple(results),
        by_event_id=by_event,
        signal_by_event_id=by_signal,
        service=service,
    )
