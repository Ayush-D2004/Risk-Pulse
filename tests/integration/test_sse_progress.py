import pytest
import asyncio
from httpx import AsyncClient
from src.dashboard.api import app, runtime_orchestrator, runtime_store
from src.integration.runtime_models import PipelineRunRequest, RunMode, ObservationInput, ObservationSource, AnalystChannel
from src.integration.runtime import RuntimeOrchestrator

@pytest.mark.asyncio
async def test_sse_progress_updates():
    # We will temporarily mock a stage in RuntimeOrchestrator to take 2 seconds
    # Then we will start a request, and while it's running, connect to SSE and see if we get the RUNNING state.

    obs = ObservationInput(
        text="A simulated event.",
        source=ObservationSource.ANALYST_SIMULATION,
        channel=AnalystChannel.NEWS,
    )
    run_req = PipelineRunRequest(
        mode=RunMode.ANALYST_SIMULATION,
        observations=[obs]
    )

    # Use the app's startup event to initialize
    import src.dashboard.api as api
    api.startup_event()
    
    # Let's mock a method inside orchestrator to be slow
    original_process = api.runtime_orchestrator._execute_pipeline
    
    events_received = []

    import time
    def mock_execute(run):
        # We manually transition to running
        from src.integration.runtime_models import PipelineStage, StageStatus
        from datetime import datetime, timezone
        
        stage = PipelineStage(name="slow_stage", status=StageStatus.RUNNING, started_at=datetime.now(timezone.utc))
        run.stages.append(stage)
        api.runtime_store.update_run(run)
        
        # Sleep to allow SSE to read
        time.sleep(2)
        
        stage.status = StageStatus.COMPLETED
        stage.completed_at = datetime.now(timezone.utc)
        api.runtime_store.update_run(run)

    api.runtime_orchestrator._execute_pipeline = mock_execute

    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Start the pipeline
        payload = {
            "mode": "ANALYST_SIMULATION",
            "observations": [
                {
                    "source": "ANALYST_SIMULATION",
                    "channel": "NEWS",
                    "headline": "Slow event",
                    "body": "Slow body"
                }
            ]
        }
        res = await client.post("/api/intelligence/simulate", json=payload)
        assert res.status_code == 200
        run_id = res.json()["run_id"]

        # Connect to SSE
        # HTTPX AsyncClient doesn't directly support SSE well but we can stream
        async with client.stream("GET", f"/api/intelligence/runs/{run_id}/stream") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    import json
                    parsed = json.loads(data)
                    events_received.append(parsed)
                    
                    if parsed.get("status") == "COMPLETED" or parsed.get("status") == "FAILED":
                        break
                    
                    # We expect to see a RUNNING stage
                    if any(s["status"] == "RUNNING" for s in parsed.get("stages", [])):
                        # Got the intermediate state!
                        pass

    # Restore
    api.runtime_orchestrator._execute_pipeline = original_process

    # Verify we got intermediate SSE events
    assert len(events_received) > 0
    running_states = [e for e in events_received if any(s["status"] == "RUNNING" for s in e.get("stages", []))]
    assert len(running_states) > 0, "SSE did not deliver intermediate RUNNING state"
