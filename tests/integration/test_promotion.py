
from fastapi.testclient import TestClient
from src.dashboard.api import app, runtime_orchestrator, runtime_store, promotion_registry
from src.integration.runtime_models import PipelineRun, PipelineRunRequest, RunMode, RunStatus, ObservationInput, ObservationSource, AnalystChannel
import pytest
import uuid

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_stores():
    conn = runtime_store.db._get_conn()
    with conn:
        conn.execute("DELETE FROM pipeline_runs")
        conn.execute("DELETE FROM promoted_runs")
        conn.execute("DELETE FROM promoted_events")
    # Also reset the read models
    promotion_registry.promoted_runs.clear()
    promotion_registry.signals.clear()
    promotion_registry.results.clear()
    promotion_registry.provenance_map.clear()
    
def create_mock_run(status=RunStatus.COMPLETED, with_result=True):
    run_id = uuid.uuid4().hex
    req = PipelineRunRequest(
        mode=RunMode.ANALYST_SIMULATION,
        observations=[ObservationInput(text="Mock text", channel=AnalystChannel.NEWS, source=ObservationSource.ANALYST_SIMULATION)]
    )
    run = PipelineRun(run_id=run_id, request=req)
    run.status = status
    if with_result:
        run.final_result = {
            "signals": [{
                "event_id": run_id,
                "entity": "MockEntity",
                "source": "ANALYST_SIMULATION",
                "sentiment_score": 0.5,
                "event_type": "NO_EVENT",
                "event_confidence": 1.0,
                "materiality": "NO_EVENT",
                "evidence": {
                    "text": "Mock text"
                }
            }],
            "stress_results": [{
                "event_id": run_id,
                "affected_entity": "MockEntity",
                "event_type": "NO_EVENT",
                "impact_score": 1.0,
                "impact_tier": "LOW",
                "rationale": "Mock",
                "stress_applied": False,
                "total_mtm_impact": "0",
                "affected_exposure_count": 0,
                "base_expected_loss": "0",
                "stressed_expected_loss": "0",
                "incremental_expected_loss": "0",
                "affected_ead": "0",
                "affected_ead_pct": 0.0,
                "stressed_exposures": []
            }]
        }
    runtime_store.add_run(run)
    return run

def test_unknown_run():
    response = client.post("/api/intelligence/runs/not-a-run/promote")
    assert response.status_code == 404

def test_non_completed_run():
    run = create_mock_run(status=RunStatus.RUNNING)
    response = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    assert response.status_code == 400
    assert "Run must be COMPLETED" in response.text

def test_missing_final_result():
    run = create_mock_run(with_result=False)
    response = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    assert response.status_code == 400
    assert "missing valid final_result" in response.text

def test_signal_stress_mismatch():
    run = create_mock_run()
    run.final_result["stress_results"] = []
    runtime_store.update_run(run)
    response = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    assert response.status_code == 400
    assert "Mismatched" in response.text

def test_successful_promotion():
    run = create_mock_run()
    response = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["promoted_event_ids"] == [run.run_id]
    
    # Check if it appears in /api/events
    events_resp = client.get("/api/events")
    events = events_resp.json()
    assert any(e["event_id"] == run.run_id for e in events)
    promoted_event = next(e for e in events if e["event_id"] == run.run_id)
    assert promoted_event["provenance"] == "ANALYST_SIMULATION"

def test_idempotent_promotion():
    run = create_mock_run()
    resp1 = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    resp2 = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "ALREADY_PROMOTED"

def test_collision_demo_fixture():
    run = create_mock_run()
    # Force collision with known demo event
    run.final_result["signals"][0]["event_id"] = "DEMO-TESLA-CREDIT-10"
    run.final_result["stress_results"][0]["event_id"] = "DEMO-TESLA-CREDIT-10"
    runtime_store.update_run(run)
    response = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    assert response.status_code == 400
    assert "Collision" in response.text

def test_collision_another_promoted_run():
    run1 = create_mock_run()
    client.post(f"/api/intelligence/runs/{run1.run_id}/promote")
    
    run2 = create_mock_run()
    # Same event ID
    run2.final_result["signals"][0]["event_id"] = run1.run_id
    run2.final_result["stress_results"][0]["event_id"] = run1.run_id
    runtime_store.update_run(run2)
    response = client.post(f"/api/intelligence/runs/{run2.run_id}/promote")
    assert response.status_code == 400
    assert "Collision" in response.text

def test_atomic_failure():
    run = create_mock_run()
    run.final_result["signals"].append({
        "event_id": "DEMO-TESLA-CREDIT-10", # This will cause a collision
        "entity": "MockEntity",
        "source": "ANALYST_SIMULATION",
        "sentiment_score": 0.5,
        "event_type": "NO_EVENT",
        "event_confidence": 1.0,
        "materiality": "NO_EVENT",
        "evidence": {
            "text": "Mock text"
        }
    })
    run.final_result["stress_results"].append({
        "event_id": "DEMO-TESLA-CREDIT-10",
        "affected_entity": "MockEntity",
        "event_type": "NO_EVENT",
        "impact_score": 1.0,
        "impact_tier": "LOW",
        "rationale": "Mock",
        "stress_applied": False,
        "total_mtm_impact": "0",
        "affected_exposure_count": 0,
        "base_expected_loss": "0",
        "stressed_expected_loss": "0",
        "incremental_expected_loss": "0",
        "affected_ead": "0",
        "affected_ead_pct": 0.0,
        "stressed_exposures": []
    })
    
    runtime_store.update_run(run)
    response = client.post(f"/api/intelligence/runs/{run.run_id}/promote")
    assert response.status_code == 400
    # Ensure it wasn't partially inserted
    assert run.run_id not in promotion_registry.signals
