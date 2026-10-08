import pytest
import asyncio
from fastapi.testclient import TestClient
from src.dashboard.api import app, runtime_store, runtime_orchestrator
from src.integration.runtime_models import RunStatus

# We need to ensure startup logic runs if we want to test the orchestrator, 
# but TestClient does not automatically call startup events if not used with 'with' block.
# Let's use it as a context manager.

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

def test_create_and_get_run(client):
    doc = {
        "channel": "NEWS",
        "headline": "Tesla goes bankrupt",
        "body": "Tesla files for bankruptcy following a severe liquidity crisis.",
        "url": "http://example.com/tesla-bankrupt",
        "author": "example.com"
    }
    
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [doc]
    }
    
    response = client.post("/api/intelligence/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    run_id = data["run_id"]
    
    # Check that we can get the run
    get_res = client.get(f"/api/intelligence/runs/{run_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["run_id"] == run_id
    assert "Tesla files for bankruptcy" in get_data["request"]["observations"][0]["text"]

@pytest.mark.asyncio
async def test_full_pipeline_execution():
    # Test the orchestrator directly to avoid waiting on the HTTP client which isn't fully async
    from src.dashboard.api import runtime_orchestrator, runtime_store
    from src.integration.runtime_models import PipelineRun, PipelineRunRequest, ObservationInput, ObservationSource, RunMode
    import uuid
    
    if not runtime_orchestrator:
        pytest.skip("RuntimeOrchestrator not initialized. Ensure tests load catalog properly.")
        
    obs = ObservationInput(
        text="Tesla secures $10B in funding for new Gigafactory.",
        headline="Tesla Funding",
        entity="Tesla",
        source=ObservationSource.ANALYST_SIMULATION
    )
    req = PipelineRunRequest(
        mode=RunMode.ANALYST_SIMULATION,
        observations=[obs]
    )
    run = PipelineRun(run_id=uuid.uuid4().hex, request=req)
    runtime_store.add_run(run)
    
    await runtime_orchestrator.process_run(run)
    
    assert run.status == RunStatus.COMPLETED
    assert run.final_result is not None
    assert len(run.stages) == 10
    for stage in run.stages:
        assert stage.status in ("COMPLETED", "SKIPPED")
        assert stage.output is not None

    signal = run.final_result["signals"][0]
    assert signal["entity"] == "Tesla"
    
def test_sse_streaming(client):
    doc = {
        "channel": "NEWS",
        "body": "Breaking news: Federal Reserve hikes interest rates."
    }
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [doc]
    }
    post_res = client.post("/api/intelligence/simulate", json=payload)
    run_id = post_res.json()["run_id"]
    
    # We can fetch the stream using stream=True and iter_lines
    with client.stream("GET", f"/api/intelligence/runs/{run_id}/stream") as response:
        # Just grab the first few events
        event_count = 0
        for line in response.iter_lines():
            if line.startswith("data: "):
                event_count += 1
                if event_count >= 2:
                    break
        assert event_count >= 1
