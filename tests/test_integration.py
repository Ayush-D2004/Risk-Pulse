import pytest
import os
import pandas as pd
from decimal import Decimal
import json

from src.integration.adapter import CanonicalEventAdapter
from src.integration.selector import select_real_event
from src.portfolio.synthetic_portfolio import generate_synthetic_portfolio
from src.portfolio.orchestration import StressScenarioEngine
from src.dashboard.service import DashboardReadService
from src.dashboard.serialization import to_jsonable
from src.risk.risk_signal import EventType

def test_canonical_event_conversion():
    """1. Valid real canonical event converts correctly."""
    row = {
        "event_id": "test_123",
        "canonical_entity": "Apple",
        "entity_status": "valid",
        "event_type": "Market / Liquidity",
        "timestamp": "2018-10-09 00:00:00+00:00",
        "sentiment_score": -0.5,
        "event_confidence": 0.8,
        "materiality": "MATERIAL_EVENT",
        "impact_score": 8.5,
        "novelty": 0.5,
        "observation_count": 10,
        "source_types": "['news']",
        "representative_source_credibility": 1.0,
        "representative_text": "Sample text",
        "representative_url": "http://example.com",
    }
    signal = CanonicalEventAdapter.from_row(row)
    
    assert signal.event_id == "test_123"  # 2. Canonical event ID is preserved
    assert signal.entity == "Apple"       # 3. Entity is preserved
    assert signal.event_type == "Market / Liquidity" # 4. Event type is preserved
    assert signal.impact_score == 8.5     # 5. Impact score is preserved
    assert signal.sentiment_score == -0.5

def test_unresolved_entities_rejected():
    """6. Unresolved source entities are rejected. 7. Unresolved entities are rejected."""
    row = {
        "event_id": "test_123",
        "canonical_entity": "Apple",
        "entity_status": "unresolved_source",
        "event_type": "Market / Liquidity",
        "timestamp": "2018-10-09 00:00:00+00:00",
        "sentiment_score": -0.5,
        "impact_score": 8.5,
    }
    with pytest.raises(ValueError, match="Cannot adapt unresolved entity status"):
        CanonicalEventAdapter.from_row(row)
        
    row["entity_status"] = "unresolved_entity"
    with pytest.raises(ValueError, match="Cannot adapt unresolved entity status"):
        CanonicalEventAdapter.from_row(row)

def test_shock_mapper_and_orchestration_invoked():
    """8. Existing ShockMapper is actually invoked. 9. Existing StressEngine/orchestration is actually invoked."""
    row = {
        "event_id": "test_123",
        "canonical_entity": "Apple",
        "entity_status": "valid",
        "event_type": "Market / Liquidity",
        "timestamp": "2018-10-09 00:00:00+00:00",
        "sentiment_score": -0.5,
        "impact_score": 8.5,
    }
    signal = CanonicalEventAdapter.from_row(row)
    
    portfolio = generate_synthetic_portfolio()
    engine = StressScenarioEngine(portfolio)
    result = engine.run_signal(signal)
    
    # 10. A real event affects the expected portfolio exposure(s)
    assert result.stress_applied is True
    assert result.shock_scenario is not None
    assert result.affected_exposure_count > 0

def test_entity_scoped_event_isolation():
    """Verify that an ENTITY-scoped event (e.g. Other / Unclear) only affects the target entity."""
    row = {
        "event_id": "test_entity_123",
        "canonical_entity": "Microsoft",
        "entity_status": "valid",
        "event_type": "Other / Unclear",
        "timestamp": "2018-08-13 00:00:00+00:00",
        "sentiment_score": -0.7,
        "impact_score": 7.91,
    }
    signal = CanonicalEventAdapter.from_row(row)
    portfolio = generate_synthetic_portfolio()
    engine = StressScenarioEngine(portfolio)
    result = engine.run_signal(signal)
    
    assert result.stress_applied is True
    assert result.shock_scenario.shock_scope == "ENTITY"
    
    affected_obligors = set()
    for exp in result.stressed_exposures:
        if exp.is_affected:
            affected_obligors.add(exp.obligor)
            
    # Microsoft only has 1 exposure in the synthetic portfolio, check that only Microsoft was affected
    assert len(affected_obligors) == 1
    assert "Microsoft" in list(affected_obligors)[0]

def test_no_event_input_does_not_create_stress():
    """11. No-event input does not create a stress."""
    row = {
        "event_id": "test_123",
        "canonical_entity": "Apple",
        "entity_status": "valid",
        "event_type": EventType.NO_EVENT.value,
        "timestamp": "2018-10-09 00:00:00+00:00",
        "sentiment_score": 0.0,
        "impact_score": 1.0,
    }
    signal = CanonicalEventAdapter.from_row(row)
    
    portfolio = generate_synthetic_portfolio()
    engine = StressScenarioEngine(portfolio)
    result = engine.run_signal(signal)
    
    assert result.stress_applied is False
    assert result.incremental_expected_loss == Decimal("0")

def test_dashboard_serialization():
    """13. Dashboard serialization succeeds. 14. Decimal values remain exact through serialization."""
    row = {
        "event_id": "test_123",
        "canonical_entity": "Apple",
        "entity_status": "valid",
        "event_type": "Market / Liquidity",
        "timestamp": "2018-10-09 00:00:00+00:00",
        "sentiment_score": -0.5,
        "impact_score": 8.5,
    }
    signal = CanonicalEventAdapter.from_row(row)
    portfolio = generate_synthetic_portfolio()
    engine = StressScenarioEngine(portfolio)
    result = engine.run_signal(signal)
    
    service = DashboardReadService(portfolio)
    dto = service.event_stress_overview(result, signal)
    jsonable = to_jsonable(dto)
    
    # Decimals should be serialized as strings
    assert isinstance(jsonable["data"]["incremental_el"], str)
    assert Decimal(jsonable["data"]["incremental_el"]) == result.incremental_expected_loss

def test_repeated_execution_deterministic():
    """15. Repeated execution is deterministic."""
    row = {
        "event_id": "test_123",
        "canonical_entity": "Apple",
        "entity_status": "valid",
        "event_type": "Market / Liquidity",
        "timestamp": "2018-10-09 00:00:00+00:00",
        "sentiment_score": -0.5,
        "impact_score": 8.5,
    }
    signal = CanonicalEventAdapter.from_row(row)
    portfolio = generate_synthetic_portfolio()
    engine = StressScenarioEngine(portfolio)
    
    result1 = engine.run_signal(signal)
    result2 = engine.run_signal(signal)
    
    assert result1.incremental_expected_loss == result2.incremental_expected_loss
    assert result1.total_mtm_impact == result2.total_mtm_impact

def test_end_to_end_integration():
    """End-to-end integration test using actual repository data/fixtures derived from the real canonical-event output."""
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "pipeline_output", "canonical_events.csv")
    if not os.path.exists(csv_path):
        pytest.skip("Data file not found")
        
    raw_event = select_real_event(csv_path)
    signal = CanonicalEventAdapter.from_row(raw_event)
    portfolio = generate_synthetic_portfolio()
    engine = StressScenarioEngine(portfolio)
    result = engine.run_signal(signal)
    
    assert result.stress_applied is True
    assert result.shock_scenario is not None
    assert result.affected_exposure_count > 0
    assert result.incremental_expected_loss > Decimal("0")
