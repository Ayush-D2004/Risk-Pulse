#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deterministic End-to-End Integration Demo
=========================================
Runs a real canonical event from the pipeline output against the synthetic portfolio,
validating the end-to-end flow.
"""

from src.integration.selector import select_real_event
from src.integration.adapter import CanonicalEventAdapter
from src.integration.models import IntegrationResult
from src.portfolio.synthetic_portfolio import generate_synthetic_portfolio
from src.portfolio.orchestration import StressScenarioEngine
from src.dashboard.service import DashboardReadService
from src.dashboard.serialization import to_jsonable
import json

def run_integration_demo(csv_path: str):
    print("1. Selecting real canonical event...")
    raw_event = select_real_event(csv_path)
    print(f"Selected Canonical Event ID: {raw_event['event_id']}")
    
    print("2. Adapting to RiskSignal domain model...")
    risk_signal = CanonicalEventAdapter.from_row(raw_event)
    
    print("3. Loading synthetic portfolio...")
    portfolio = generate_synthetic_portfolio()
    
    print("4. Running Stress Orchestration Engine...")
    engine = StressScenarioEngine(portfolio)
    result = engine.run_signal(risk_signal)
    
    # Check if a stress scenario actually generated
    if not result.shock_scenario:
        print(f"Failed to generate stress scenario! Error: {result.error}")
        return

    integration_result = IntegrationResult(
        signal=risk_signal,
        scenario=result.shock_scenario,
        orchestration_result=result
    )
    
    print("\n5. Traceability Report:")
    print(integration_result.generate_trace_report())
    
    print("\n6. Dashboard DTO Serialization Check...")
    service = DashboardReadService(portfolio)
    
    # We can serialize using the dashboard read service
    dto = service.event_stress_overview(result, risk_signal)
    json_output = json.dumps(to_jsonable(dto), indent=2)
    print(f"Successfully serialized to DTO (length: {len(json_output)} bytes)")
    
    return integration_result

if __name__ == "__main__":
    import os
    import argparse
    
    parser = argparse.ArgumentParser(description="Deterministic End-to-End Integration Demo")
    parser.add_argument(
        "--canonical-events", 
        type=str, 
        default=os.path.join("data", "pipeline_output", "canonical_events.csv"),
        help="Path to the canonical events CSV file"
    )
    args = parser.parse_args()
    
    csv_path = args.canonical_events
    if os.path.exists(csv_path):
        run_integration_demo(csv_path)
    else:
        print(f"Could not find {csv_path}")
