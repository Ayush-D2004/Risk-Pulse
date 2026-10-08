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

from src.integration.runtime_models import PipelineRun, RunStatus, RunMode, AnalystChannel, ObservationSource, ObservationInput, PipelineRunRequest
from src.integration.runtime_store import RuntimeStore
from src.integration.runtime import RuntimeOrchestrator
from src.integration.gdelt_service import GDELTIntegrationService
from pydantic import BaseModel

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
gdelt_service = None

@app.on_event("startup")
def startup_event():
    global runtime_orchestrator, gdelt_service
    try:
        runtime_orchestrator = RuntimeOrchestrator(
            store=runtime_store,
            portfolio=catalog.service._portfolio,
            device="cpu"
        )
        gdelt_service = GDELTIntegrationService(
            orchestrator=runtime_orchestrator,
            store=runtime_store
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

from datetime import datetime
from typing import Dict, Any, Optional, List

class AnalystObservation(BaseModel):
    source: ObservationSource = ObservationSource.ANALYST_SIMULATION
    channel: AnalystChannel
    author: Optional[str] = None
    headline: Optional[str] = None
    body: Optional[str] = None
    timestamp: Optional[datetime] = None
    url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class AnalystSimulationRequest(BaseModel):
    mode: RunMode = RunMode.ANALYST_SIMULATION
    observations: List[AnalystObservation]

@app.post("/api/intelligence/simulate")
async def simulate_runs(req: AnalystSimulationRequest):
    if not runtime_orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
        
    if not req.observations:
        raise HTTPException(status_code=400, detail="Observations cannot be empty")
        
    obs_inputs = []
    for obs in req.observations:
        text_parts = []
        if obs.headline:
            text_parts.append(obs.headline.strip())
        if obs.body:
            text_parts.append(obs.body.strip())
            
        text = " ".join(text_parts)
        if not text.strip():
            raise HTTPException(status_code=400, detail="Observation must have text (headline or body)")
            
        obs_inputs.append(ObservationInput(
            text=text,
            headline=obs.headline,
            url=obs.url,
            author=obs.author,
            entity=None,
            source=ObservationSource.ANALYST_SIMULATION,
            timestamp=obs.timestamp,
            channel=obs.channel,
            metadata=obs.metadata
        ))
        
    run_req = PipelineRunRequest(
        mode=RunMode.ANALYST_SIMULATION,
        observations=obs_inputs
    )
    
    run_id = uuid.uuid4().hex
    run = PipelineRun(
        run_id=run_id,
        request=run_req,
    )
    
    runtime_store.add_run(run)
    asyncio.create_task(runtime_orchestrator.process_run(run))
    
    return {"run_id": run_id, "status": run.status}

class GDELTSearchRequest(BaseModel):
    query: str
    max_records: int = 50

@app.post("/api/intelligence/gdelt/search")
async def search_gdelt(req: GDELTSearchRequest):
    if not gdelt_service:
        raise HTTPException(status_code=503, detail="GDELT service not initialized")
        
    result = gdelt_service.submit_search(query=req.query, max_records=req.max_records)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

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

