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
from src.dashboard.promotion import PromotionRegistry, PromotedRunResponse
from src.ingestion.worker import GDELTWorker, GDELTWorkerConfig
from src.db import db_instance
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
gdelt_worker = None
promotion_registry = PromotionRegistry()

@app.on_event("startup")
def startup_event():
    global runtime_orchestrator, gdelt_service, gdelt_worker
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
        # Initialize worker (disabled by default)
        config = GDELTWorkerConfig(enabled=False)
        gdelt_worker = GDELTWorker(gdelt_service, config)
        gdelt_worker.start()
    except Exception as e:
        print(f"Failed to initialize RuntimeOrchestrator or Worker: {e}")

@app.on_event("shutdown")
def shutdown_event():
    if gdelt_worker:
        gdelt_worker.stop()

@app.get("/api/intelligence/worker/status")
def get_worker_status():
    conn = db_instance._get_conn()
    row = conn.execute("SELECT * FROM gdelt_worker_status WHERE id = 1").fetchone()
    return {
        "enabled": gdelt_worker.config.enabled if gdelt_worker else False,
        "last_attempt_at": row["last_attempt_at"] if row else None,
        "last_success_at": row["last_success_at"] if row else None,
        "last_result_category": row["last_result_category"] if row else None,
        "fetched_count": row["fetched_count"] if row else 0,
        "deduped_count": row["deduped_count"] if row else 0,
        "submitted_count": row["submitted_count"] if row else 0,
        "active_run_id": row["active_run_id"] if row else None,
    }

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
            
    for event_id, s in promotion_registry.signals.items():
        result = promotion_registry.results.get(event_id)
        if result:
            events.append(project_event_overview(result, s, promotion_registry.provenance_map.get(event_id)))
            
    return events

@app.get("/api/scenarios/{event_id}", response_model=EventStressOverviewResponse)
def get_scenario_overview(event_id: str):
    if event_id in promotion_registry.signals:
        result = promotion_registry.results[event_id]
        signal = promotion_registry.signals[event_id]
        prov = promotion_registry.provenance_map.get(event_id)
        return catalog.service.event_stress_overview(result, signal, provenance=prov)
        
    if event_id not in catalog.by_event_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    result = catalog.by_event_id[event_id]
    signal = catalog.signal_by_event_id[event_id]
    return catalog.service.event_stress_overview(result, signal)

@app.get("/api/scenarios/{event_id}/attribution", response_model=RiskAttributionResponse)
def get_scenario_attribution(event_id: str):
    if event_id in promotion_registry.results:
        result = promotion_registry.results[event_id]
        return catalog.service.risk_attribution(result)
        
    if event_id not in catalog.by_event_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    result = catalog.by_event_id[event_id]
    return catalog.service.risk_attribution(result)

@app.get("/api/compare/{event_a}/{event_b}", response_model=ScenarioComparisonResponse)
def get_scenario_comparison(event_a: str, event_b: str):
    # Lookup A
    if event_a in promotion_registry.results:
        res_a = promotion_registry.results[event_a]
        sig_a = promotion_registry.signals[event_a]
        setattr(sig_a, "_provenance", promotion_registry.provenance_map.get(event_a))
    elif event_a in catalog.by_event_id:
        res_a = catalog.by_event_id[event_a]
        sig_a = catalog.signal_by_event_id[event_a]
    else:
        raise HTTPException(status_code=404, detail=f"Scenario A not found: {event_a}")
        
    # Lookup B
    if event_b in promotion_registry.results:
        res_b = promotion_registry.results[event_b]
        sig_b = promotion_registry.signals[event_b]
        setattr(sig_b, "_provenance", promotion_registry.provenance_map.get(event_b))
    elif event_b in catalog.by_event_id:
        res_b = catalog.by_event_id[event_b]
        sig_b = catalog.signal_by_event_id[event_b]
    else:
        raise HTTPException(status_code=404, detail=f"Scenario B not found: {event_b}")
        
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
    entity: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class AnalystSimulationRequest(BaseModel):
    mode: RunMode = RunMode.ANALYST_SIMULATION
    company_name: Optional[str] = None
    ticker: Optional[str] = None
    event_datetime: Optional[str] = None  # ISO format string or similar
    timezone: Optional[str] = None
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
            
        # Merge global metadata into observation metadata
        merged_meta = dict(obs.metadata) if obs.metadata is not None else None
        if req.company_name or req.ticker or req.event_datetime or req.timezone:
            merged_meta = merged_meta or {}
            if req.company_name:
                merged_meta["company_name"] = req.company_name
            if req.ticker:
                merged_meta["ticker"] = req.ticker
            if req.event_datetime:
                merged_meta["event_datetime"] = req.event_datetime
            if req.timezone:
                merged_meta["timezone"] = req.timezone
            
        obs_inputs.append(ObservationInput(
            text=text,
            headline=obs.headline,
            url=obs.url,
            author=obs.author,
            entity=req.company_name or obs.entity,
            source=ObservationSource.ANALYST_SIMULATION,
            timestamp=obs.timestamp,
            channel=obs.channel,
            metadata=merged_meta
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

@app.post("/api/intelligence/runs/{run_id}/promote", response_model=PromotedRunResponse)
def promote_run(run_id: str):
    run = runtime_store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    existing_event_ids = frozenset(catalog.by_event_id.keys())
    try:
        response = promotion_registry.promote(run, existing_event_ids)
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

from src.market.yfinance_client import MarketDataService

@app.get("/api/market/historical")
async def get_historical_market_data(
    ticker: str,
    timestamp: str,
    timezone: str = "UTC",
    window_hours: int = 4
):
    """Fetch historical intraday/daily stock prices around an event."""
    if not ticker or not timestamp:
        raise HTTPException(status_code=400, detail="Ticker and timestamp are required")
        
    result = await MarketDataService.fetch_historical_window(
        ticker=ticker,
        event_dt_str=timestamp,
        tz_name=timezone,
        window_hours=window_hours
    )
    
    if result.get("status") == "error":
        raise HTTPException(status_code=502, detail=result.get("reason", "Unknown error"))
        
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
        last_dump = None
        heartbeat_counter = 0
        while True:
            if await request.is_disconnected():
                break
                
            current_run = runtime_store.get_run(run_id)
            if not current_run:
                break
                
            # Yield full current state on change or periodic heartbeat
            data = current_run.model_dump(mode="json")
            dump_str = json.dumps(data)
            heartbeat_counter += 1

            if dump_str != last_dump or heartbeat_counter >= 15:
                yield f"data: {dump_str}\n\n"
                last_dump = dump_str
                heartbeat_counter = 0
            
            if current_run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                # Ensure terminal state is yielded
                if dump_str != last_dump:
                    yield f"data: {dump_str}\n\n"
                break
                
            await asyncio.sleep(0.1)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

