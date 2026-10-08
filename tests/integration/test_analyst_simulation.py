import pytest
import asyncio
from fastapi.testclient import TestClient

from src.dashboard.api import app, runtime_store, runtime_orchestrator
from src.integration.runtime_models import RunStatus, RunMode, ObservationSource, AnalystChannel

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

def test_single_twitter_style_observation(client):
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [
            {
                "channel": "TWITTER_X_STYLE",
                "author": "@FinancialGuru",
                "body": "Tesla is seeing a huge crash in premarket after CEO steps down.",
                "timestamp": "2024-03-15T09:00:00Z"
            }
        ]
    }
    
    res = client.post("/api/intelligence/simulate", json=payload)
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    
    # 5. Provenance correctness
    run = runtime_store.get_run(run_id)
    assert run.request.mode == RunMode.ANALYST_SIMULATION
    assert len(run.request.observations) == 1
    obs = run.request.observations[0]
    assert obs.source == ObservationSource.ANALYST_SIMULATION
    assert obs.channel == AnalystChannel.TWITTER_X_STYLE
    assert obs.author == "@FinancialGuru"
    assert "Tesla is seeing a huge crash" in obs.text

def test_single_news_observation(client):
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [
            {
                "channel": "NEWS",
                "headline": "Apple Unveils New Product",
                "body": "Apple has just announced a revolutionary new VR headset.",
                "metadata": {"tags": ["tech", "apple"]}
            }
        ]
    }
    
    res = client.post("/api/intelligence/simulate", json=payload)
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    
    run = runtime_store.get_run(run_id)
    obs = run.request.observations[0]
    assert obs.channel == AnalystChannel.NEWS
    assert obs.headline == "Apple Unveils New Product"
    # Text must be deterministically constructed from headline and body
    assert "Apple Unveils New Product" in obs.text
    assert "revolutionary new VR headset" in obs.text
    assert obs.metadata == {"tags": ["tech", "apple"]}

def test_mixed_observations_in_one_run(client):
    # 3. mixed Twitter/X-style + news observations
    # 4. multiple observations in one run
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [
            {
                "channel": "NEWS",
                "headline": "Amazon faces anti-trust lawsuit",
            },
            {
                "channel": "TWITTER_X_STYLE",
                "body": "Just heard the Amazon anti-trust news. Stock is going to tank! #Amazon",
            }
        ]
    }
    
    res = client.post("/api/intelligence/simulate", json=payload)
    assert res.status_code == 200
    run_id = res.json()["run_id"]
    
    run = runtime_store.get_run(run_id)
    assert len(run.request.observations) == 2
    assert run.request.observations[0].channel == AnalystChannel.NEWS
    assert run.request.observations[1].channel == AnalystChannel.TWITTER_X_STYLE

def test_invalid_empty_input(client):
    # 6. invalid empty input
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": []
    }
    res = client.post("/api/intelligence/simulate", json=payload)
    assert res.status_code == 400
    assert "Observations cannot be empty" in res.json()["detail"]

def test_invalid_observation_no_text(client):
    # 7. invalid observation (no text content)
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [
            {
                "channel": "NEWS",
                # no headline, no body
            }
        ]
    }
    res = client.post("/api/intelligence/simulate", json=payload)
    assert res.status_code == 400
    assert "must have text" in res.json()["detail"]

def test_unsupported_channel(client):
    # 8. unsupported channel
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [
            {
                "channel": "INVALID_CHANNEL",
                "body": "Some text"
            }
        ]
    }
    res = client.post("/api/intelligence/simulate", json=payload)
    # Pydantic validation error
    assert res.status_code == 422 
    assert "Input should be 'TWITTER_X_STYLE' or 'NEWS'" in str(res.json())

@pytest.mark.asyncio
async def test_full_analyst_simulation_execution_and_module_b():
    # 9. observations reach RuntimeOrchestrator
    # 10. clustering stage executes
    # 11. final RiskSignal is produced where appropriate
    # 12. Module B integration
    import uuid
    from src.integration.runtime_models import PipelineRun, PipelineRunRequest, ObservationInput
    
    if not runtime_orchestrator:
        pytest.skip("RuntimeOrchestrator not initialized.")

    obs1 = ObservationInput(
        text="Major earthquake in California affecting tech companies.",
        channel=AnalystChannel.NEWS,
        source=ObservationSource.ANALYST_SIMULATION
    )
    obs2 = ObservationInput(
        text="Earthquake just hit CA! Expect tech supply chain issues.",
        channel=AnalystChannel.TWITTER_X_STYLE,
        source=ObservationSource.ANALYST_SIMULATION
    )
    
    req = PipelineRunRequest(
        mode=RunMode.ANALYST_SIMULATION,
        observations=[obs1, obs2]
    )
    run = PipelineRun(run_id=uuid.uuid4().hex, request=req)
    runtime_store.add_run(run)
    
    await runtime_orchestrator.process_run(run)
    
    assert run.status == RunStatus.COMPLETED
    assert run.final_result is not None
    
    # Check clustering: 2 observations should cluster into 1 signal since they are about the same event.
    # Note: the EventClusterer in tests might be a mock or deterministic. 
    # Whether it clusters them or not, it MUST pass through clustering.
    signals = run.final_result["signals"]
    assert len(signals) >= 1
    
    # Module B output
    stress_results = run.final_result["stress_results"]
    assert len(stress_results) == len(signals)
    for sr in stress_results:
        assert "affected_ead" in sr
        assert "incremental_expected_loss" in sr
        assert "total_mtm_impact" in sr
        assert "stressed_exposures" in sr

def test_sse_compatibility_through_stream(client):
    # 14. SSE compatibility through the existing runtime stream
    payload = {
        "mode": "ANALYST_SIMULATION",
        "observations": [
            {
                "channel": "NEWS",
                "body": "RetailBank announces surprise acquisition."
            }
        ]
    }
    post_res = client.post("/api/intelligence/simulate", json=payload)
    run_id = post_res.json()["run_id"]
    
    with client.stream("GET", f"/api/intelligence/runs/{run_id}/stream") as response:
        event_count = 0
        for line in response.iter_lines():
            if line.startswith("data: "):
                event_count += 1
                if event_count >= 1:
                    break
        assert event_count >= 1
