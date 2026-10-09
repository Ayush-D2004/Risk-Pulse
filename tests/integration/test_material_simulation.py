import pytest
import time
from fastapi.testclient import TestClient
from src.dashboard.api import app, runtime_store
from src.integration.runtime_models import RunStatus

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

def test_material_event_stress_results(client):
    payload = {
        "mode": "ANALYST_SIMULATION",
        "company_name": "Apple Inc.",
        "ticker": "AAPL",
        "event_datetime": "2024-03-01T10:00:00",
        "timezone": "UTC",
        "observations": [
            {
                "channel": "NEWS",
                "headline": "Apple fined $2 billion by EU antitrust regulators.",
                "body": "European regulators levied a massive $2 billion penalty on Apple.",
            }
        ]
    }
    
    res = client.post("/api/intelligence/simulate", json=payload)
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    
    # Wait for the background process to complete
    for _ in range(50):
        run = runtime_store.get_run(run_id)
        if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
            break
        time.sleep(0.5)
        
    assert run.status == RunStatus.COMPLETED
    assert run.final_result is not None
    
    signals = run.final_result["signals"]
    assert len(signals) > 0
    signal = signals[0]
    assert signal["event_type"] == "Regulatory / Legal"
    assert signal["materiality"] == "MATERIAL_EVENT"
    
    stress_results = run.final_result["stress_results"]
    assert len(stress_results) > 0
    stress = stress_results[0]
    
    # Assert that stress was successfully applied and not 0 everywhere
    assert stress["stress_applied"] is True
    assert float(stress["affected_ead"]) > 0
