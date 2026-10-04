from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from src.dashboard.demo import build_demo_catalog
from src.dashboard.models import (
    PortfolioOverviewResponse,
    EventStressOverviewResponse,
    RiskAttributionResponse,
    ScenarioComparisonResponse,
)

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

@app.get("/api/portfolio", response_model=PortfolioOverviewResponse)
def get_portfolio_overview():
    return catalog.service.portfolio_overview()

@app.get("/api/events")
def get_events():
    return [{"event_id": s.event_id, "type": s.event_type, "impact": s.impact_score} for s in catalog.signals]

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
