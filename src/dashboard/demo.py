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
    evidence_text: Optional[str] = None,
    headline: Optional[str] = None,
) -> RiskSignal:
    text = evidence_text or "Deterministic dashboard demo fixture"
    return RiskSignal(
        event_id=event_id,
        entity=entity,
        source="demo",
        sentiment_score=sentiment_score,
        event_type=event_type,
        event_confidence=1.0,
        materiality="MATERIAL_EVENT" if event_type != EventType.NO_EVENT.value else "NO_EVENT",
        impact_score=impact_score,
        evidence=Evidence(text=text, headline=headline),
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
            headline="Tesla Slashed to Speculative Grade Amid Liquidity Crunch and Debt Default",
            evidence_text="Major credit agency slashes Tesla debt to CCC following unexpected debt service default on offshore notes and acute liquidity contraction, triggering cross-default covenants and severe bond and equity valuation write-downs.",
        ),
        _signal(
            "DEMO-COMMODITY-PETRO",
            EventType.COMMODITY_SUPPLY_CHAIN.value,
            9.2,
            "PetroGlobal",
            -0.88,
            headline="Persian Gulf Shipping Blockade Sparks 35% Crude Oil Spike and Refinery Squeeze",
            evidence_text="Critical maritime chokepoint closure halts crude export deliveries, causing severe feed-stock shortages and operational margin compression across all wholesale banking book Energy obligors.",
        ),
        _signal(
            "DEMO-REGULATORY-APPLE",
            EventType.REGULATORY_LEGAL.value,
            8.5,
            "Apple",
            -0.92,
            headline="EU & US Regulators Impose Historic $14B Antitrust Penalty and Injunction on Apple",
            evidence_text="Antitrust authorities levy unprecedented structural remedies and multi-billion punitive fines against Apple, compressing operating margins and triggering debt spread widening across its corporate loan and bond facilities.",
        ),
        _signal(
            EVENT_GEOPOLITICAL,
            EventType.GEOPOLITICAL.value,
            8.0,
            "Germany",
            -0.85,
            headline="Eastern European Pipeline Embargo Triggers Energy Crisis and Sovereign Yield Surge",
            evidence_text="Emergency natural gas sanctions and regional supply cutoffs drive sharp inflationary surges and sovereign yield spikes across EMEA banking book assets.",
        ),
        _signal(
            "DEMO-MA-AMAZON",
            EventType.MERGER_ACQUISITION.value,
            8.2,
            "Amazon",
            0.60,
            headline="Amazon Unveils $45B Debt-Financed Acquisition of Global Logistics Carrier",
            evidence_text="Aggressive debt-financed acquisition expands corporate leverage and introduces substantial integration execution risk, prompting debt credit spread widening and equity re-pricing.",
        ),
        _signal(
            EVENT_TESLA_CREDIT_8,
            EventType.CREDIT_EVENT.value,
            8.0,
            "Tesla",
            -0.85,
            headline="Tesla Downgraded by Two Notches on Auto Margin Compression",
            evidence_text="Rating agency initiates two-notch downgrade following automotive gross margin deterioration and aggressive EV price cuts, stressing credit spreads.",
        ),
        _signal(
            EVENT_NO_EVENT,
            EventType.NO_EVENT.value,
            1.0,
            "Apple",
            0.0,
            headline="Apple Announces Routine Minor Accessory Colorway Updates",
            evidence_text="Routine product color refresh generates non-material financial commentary with zero structural impact on obligor creditworthiness or portfolio debt facilities.",
        ),
        _signal(
            "TEST-MARKET-DAMPENING",
            EventType.CREDIT_EVENT.value,
            6.5,  # Dampened from 9.5 due to market modifier
            "Tesla",
            -0.85,
            evidence_text="Credit event observed alongside elevated market volatility.",
        ),
        _signal(
            "TEST-NOVELTY-HIGH",
            EventType.GEOPOLITICAL.value,
            9.0,  # High impact due to novelty = 1.0
            "Germany",
            -0.80,
            evidence_text="Novel geopolitical conflict outbreak in Western Europe.",
        ),
        _signal(
            "TEST-GUARDRAIL-BLOCKED",
            EventType.CREDIT_EVENT.value,
            1.5,  # Impact slashed because financial guardrail blocked it
            "MidCapCorp",
            -0.90,
            evidence_text="Spurious credit alarm dampened by financial balance sheet guardrails.",
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
