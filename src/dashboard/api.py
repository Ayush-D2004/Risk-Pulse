from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import uuid
from typing import List

from src.dashboard.demo import build_demo_catalog
from src.dashboard.models import (
    PortfolioOverviewResponse,
    EventStressOverviewResponse,
    RiskAttributionResponse,
    ScenarioComparisonResponse,
)

from src.integration.runtime_models import PipelineRun, RunStatus, RunMode
from src.integration.runtime_store import RuntimeStore
from src.integration.runtime import RuntimeOrchestrator
from src.integration.observation_adapter import NewsDocument, adapt_to_run_request

app = FastAPI(title="RiskPulse Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load catalog once at startup
catalog = build_demo_catalog()

# Runtime Orchestration dependencies
runtime_store = RuntimeStore()
runtime_orchestrator = None

@app.on_event("startup")
def startup_event():
    global runtime_orchestrator
    try:
        runtime_orchestrator = RuntimeOrchestrator(
            store=runtime_store,
            portfolio=catalog.service._portfolio,
            device="cpu"
        )
    except Exception as e:
        print(f"Failed to initialize RuntimeOrchestrator: {e}")

@app.get("/api/portfolio", response_model=PortfolioOverviewResponse)
def get_portfolio_overview():
    return catalog.service.portfolio_overview()

from src.dashboard.service import project_event_overview

@app.get("/api/events")
def get_events():
    events = []
    for s in catalog.signals:
        result = catalog.by_event_id.get(s.event_id)
        if result:
            events.append(project_event_overview(result, s))
    return events

@app.get("/api/scenarios/{event_id}", response_model=EventStressOverviewResponse)
def get_scenario_overview(event_id: str):
    if event_id not in catalog.by_event_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    result = catalog.by_event_id[event_id]
    signal = catalog.signal_by_event_id[event_id]
    return catalog.service.event_stress_overview(result, signal)

@app.get("/api/scenarios/{event_id}/attribution", response_model=RiskAttributionResponse)
def get_scenario_attribution(event_id: str):
    if event_id not in catalog.by_event_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    result = catalog.by_event_id[event_id]
    return catalog.service.risk_attribution(result)

@app.get("/api/compare/{event_a}/{event_b}", response_model=ScenarioComparisonResponse)
def get_scenario_comparison(event_a: str, event_b: str):
    if event_a not in catalog.by_event_id or event_b not in catalog.by_event_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    res_a = catalog.by_event_id[event_a]
    res_b = catalog.by_event_id[event_b]
    sig_a = catalog.signal_by_event_id[event_a]
    sig_b = catalog.signal_by_event_id[event_b]
    return catalog.service.scenario_comparison(res_a, res_b, sig_a, sig_b)

# --- Runtime Intelligence Endpoints ---

@app.post("/api/intelligence/runs")
async def create_run(docs: List[NewsDocument] = Body(...), mode: RunMode = RunMode.ANALYST_SIMULATION):
    if not runtime_orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
        
    req = adapt_to_run_request(docs, mode=mode)
    run_id = uuid.uuid4().hex
    
    run = PipelineRun(
        run_id=run_id,
        request=req,
    )
    
    runtime_store.add_run(run)
    asyncio.create_task(runtime_orchestrator.process_run(run))
    
    return {"run_id": run_id, "status": run.status}

@app.get("/api/intelligence/runs")
def list_runs():
    runs = runtime_store.get_all_runs()
    return {"runs": [r.model_dump(mode="json") for r in runs]}

@app.get("/api/intelligence/runs/{run_id}")
def get_run(run_id: str):
    run = runtime_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.model_dump(mode="json")

@app.get("/api/intelligence/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request):
    run = runtime_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    async def event_generator():
        last_yielded_stages = 0
        while True:
            if await request.is_disconnected():
                break
                
            # Yield full current state
            data = run.model_dump(mode="json")
            yield f"data: {json.dumps(data)}\n\n"
            
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                break
                
            await asyncio.sleep(0.5)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

