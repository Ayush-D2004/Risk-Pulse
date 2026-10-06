#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-End Integration Result Model
===================================
Models the final outcome of the integration, composing the RiskSignal
and the StressedPortfolio.
"""

from typing import Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field
from src.risk.risk_signal import RiskSignal
from src.portfolio.orchestration_models import StressScenarioResult
from src.portfolio.shock_models import ShockScenario
from decimal import Decimal

class IntegrationResult(BaseModel):
    """
    Explicit integration-level result model.
    Contains enough information to trace SOURCE, RISK, and STRESS.
    """
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )
    
    # Source & Risk (composed via RiskSignal)
    signal: RiskSignal = Field(
        ...,
        description="The adapted RiskSignal representing the canonical event."
    )
    
    # Shock (composed via ShockScenario)
    scenario: ShockScenario = Field(
        ...,
        description="The deterministic ShockScenario produced by the ShockMapper."
    )
    
    # Stress (composed via StressScenarioResult)
    orchestration_result: StressScenarioResult = Field(
        ...,
        description="The final stress testing results across the portfolio."
    )
    
    def generate_trace_report(self) -> str:
        """Generates a concise trace report of the end-to-end execution path."""
        s = self.signal
        or_res = self.orchestration_result
        sc = self.scenario
        
        trace = []
        trace.append("=== TRACEABILITY REPORT ===")
        trace.append(f"Canonical Event ID: {s.event_id}")
        trace.append(f"Entity: {s.entity}")
        trace.append(f"Event Type: {s.event_type}")
        trace.append(f"Sentiment: {s.sentiment_score}")
        trace.append(f"Impact: {s.impact_score}")
        trace.append(f"Market Context: {s.market_context is not None}")
        trace.append(f"Shock Scope: {sc.shock_scope}")
        trace.append(f"Affected EAD: {or_res.affected_ead}")
        trace.append(f"Incremental EL: {or_res.incremental_expected_loss}")
        trace.append(f"MTM Impact: {or_res.total_mtm_impact}")
        trace.append(f"Affected Exposure Count: {or_res.affected_exposure_count}")
        return "\n".join(trace)

