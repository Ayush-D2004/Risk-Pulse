import os
import pytest
import sqlite3
import tempfile
import uuid
import json
from datetime import datetime, timezone

from src.db import DatabaseLayer
from src.integration.runtime_models import PipelineRun, PipelineRunRequest, RunMode, ObservationInput, RunStatus, PipelineStage, StageStatus, AnalystChannel, ObservationSource
from src.integration.runtime_store import RuntimeStore
from src.dashboard.promotion import PromotionRegistry
from src.risk.risk_signal import RiskSignal
from src.portfolio.orchestration_models import StressScenarioResult

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    db = DatabaseLayer(db_path=path)
    yield db
    db._get_conn().close()
    if os.path.exists(path):
        try:
            os.remove(path)
        except PermissionError:
            pass

def test_pipeline_run_persistence(temp_db):
    store = RuntimeStore(db=temp_db)
    
    run_id = uuid.uuid4().hex
    req = PipelineRunRequest(
        mode=RunMode.ANALYST_SIMULATION,
        observations=[ObservationInput(text="Market drops", source=ObservationSource.ANALYST_SIMULATION, channel=AnalystChannel.NEWS)]
    )
    run = PipelineRun(run_id=run_id, request=req, status=RunStatus.COMPLETED)
    run.final_result = {"signals": [], "stress_results": []}
    run.completed_at = datetime.now(timezone.utc)
    
    store.add_run(run)
    
    # Reload from DB
    new_store = RuntimeStore(db=DatabaseLayer(db_path=temp_db.db_path))
    recovered_run = new_store.get_run(run_id)
    
    assert recovered_run is not None
    assert recovered_run.run_id == run_id
    assert recovered_run.status == RunStatus.COMPLETED
    assert recovered_run.request.mode == RunMode.ANALYST_SIMULATION
    assert recovered_run.final_result == run.final_result
    assert recovered_run.completed_at == run.completed_at

def test_interrupted_run_recovery(temp_db):
    store = RuntimeStore(db=temp_db)
    
    run_id = uuid.uuid4().hex
    req = PipelineRunRequest(mode=RunMode.ANALYST_SIMULATION, observations=[ObservationInput(text="test")])
    run = PipelineRun(run_id=run_id, request=req, status=RunStatus.RUNNING)
    store.add_run(run)
    
    # Reload
    new_store = RuntimeStore(db=DatabaseLayer(db_path=temp_db.db_path))
    recovered_run = new_store.get_run(run_id)
    
    assert recovered_run.status == RunStatus.FAILED
    assert "interrupted" in recovered_run.error.lower()

def test_promotion_persistence_and_idempotency(temp_db):
    store = RuntimeStore(db=temp_db)
    registry = PromotionRegistry(db=temp_db)
    
    run_id = uuid.uuid4().hex
    event_id = uuid.uuid4().hex
    
    req = PipelineRunRequest(mode=RunMode.ANALYST_SIMULATION, observations=[ObservationInput(text="test")])
    run = PipelineRun(run_id=run_id, request=req, status=RunStatus.COMPLETED)
    
    sig = RiskSignal(event_id=event_id, entity="Test", source=ObservationSource.ANALYST_SIMULATION.value, sentiment_score=0.5, event_type="TEST", event_confidence=1.0, materiality="HIGH", timestamp=datetime.now(), evidence={})
    res = StressScenarioResult(
        event_id=event_id,
        affected_entity="Test",
        event_type="TEST",
        impact_score=50,
        impact_tier="MODERATE",
        stressed_exposures=[],
        stress_applied=False,
        rationale="Test",
        total_mtm_impact="0",
        affected_exposure_count=0,
        base_expected_loss="0",
        stressed_expected_loss="0",
        incremental_expected_loss="0",
        affected_ead="0",
        affected_ead_pct=0.0
    )
    
    run.final_result = {
        "signals": [sig.model_dump()],
        "stress_results": [res.model_dump(mode="json")]
    }
    
    store.add_run(run)
    
    # Promote
    resp = registry.promote(run, existing_event_ids=frozenset())
    assert resp.status == "SUCCESS"
    assert event_id in resp.promoted_event_ids
    
    # Idempotency
    resp2 = registry.promote(run, existing_event_ids=frozenset())
    assert resp2.status == "ALREADY_PROMOTED"
    
    # Reload
    new_registry = PromotionRegistry(db=DatabaseLayer(db_path=temp_db.db_path))
    assert run_id in new_registry.promoted_runs
    assert event_id in new_registry.signals
    assert event_id in new_registry.results
    
    # Promote again after reload
    resp3 = new_registry.promote(run, existing_event_ids=frozenset())
    assert resp3.status == "ALREADY_PROMOTED"

def test_fixture_collision(temp_db):
    registry = PromotionRegistry(db=temp_db)
    run_id = uuid.uuid4().hex
    event_id = "FIXTURE_1"
    req = PipelineRunRequest(mode=RunMode.ANALYST_SIMULATION, observations=[ObservationInput(text="test")])
    run = PipelineRun(run_id=run_id, request=req, status=RunStatus.COMPLETED)
    
    sig = RiskSignal(event_id=event_id, entity="Test", source=ObservationSource.ANALYST_SIMULATION.value, sentiment_score=0.5, event_type="TEST", event_confidence=1.0, materiality="HIGH", timestamp=datetime.now(), evidence={})
    res = StressScenarioResult(
        event_id=event_id,
        affected_entity="Test",
        event_type="TEST",
        impact_score=50,
        impact_tier="MODERATE",
        stressed_exposures=[],
        stress_applied=False,
        rationale="Test",
        total_mtm_impact="0",
        affected_exposure_count=0,
        base_expected_loss="0",
        stressed_expected_loss="0",
        incremental_expected_loss="0",
        affected_ead="0",
        affected_ead_pct=0.0
    )
    
    run.final_result = {
        "signals": [sig.model_dump()],
        "stress_results": [res.model_dump(mode="json")]
    }
    
    with pytest.raises(ValueError, match="Collision with demo fixture"):
        registry.promote(run, existing_event_ids=frozenset([event_id]))

def test_mid_transaction_failure_rollback(temp_db):
    registry = PromotionRegistry(db=temp_db)
    run_id = uuid.uuid4().hex
    event_id = uuid.uuid4().hex
    
    req = PipelineRunRequest(mode=RunMode.ANALYST_SIMULATION, observations=[ObservationInput(text="test")])
    run = PipelineRun(run_id=run_id, request=req, status=RunStatus.COMPLETED)
    
    sig = RiskSignal(event_id=event_id, entity="Test", source=ObservationSource.ANALYST_SIMULATION.value, sentiment_score=0.5, event_type="TEST", event_confidence=1.0, materiality="HIGH", timestamp=datetime.now(), evidence={})
    res = StressScenarioResult(
        event_id=event_id,
        affected_entity="Test",
        event_type="TEST",
        impact_score=50,
        impact_tier="MODERATE",
        stressed_exposures=[],
        stress_applied=False,
        rationale="Test",
        total_mtm_impact="0",
        affected_exposure_count=0,
        base_expected_loss="0",
        stressed_expected_loss="0",
        incremental_expected_loss="0",
        affected_ead="0",
        affected_ead_pct=0.0
    )
    
    run.final_result = {
        "signals": [sig.model_dump()],
        "stress_results": [res.model_dump(mode="json")]
    }
    
    # Insert conflict using a separate connection
    conflict_conn = sqlite3.connect(temp_db.db_path)
    with conflict_conn:
        conflict_conn.execute("INSERT INTO promoted_runs (run_id, mode, source, channel, promoted_at, event_ids_json) VALUES (?, ?, ?, ?, ?, ?)", ("dummy", "ANALYST_SIMULATION", "test", "test", 0.0, "[]"))
        conflict_conn.execute("INSERT INTO promoted_events (event_id, run_id, signal_payload, result_payload, provenance) VALUES (?, ?, ?, ?, ?)", (event_id, "dummy", "{}", "{}", "prov"))
    conflict_conn.close()
    
    with pytest.raises(ValueError, match="collision|integrity"):
        registry.promote(run, existing_event_ids=frozenset())
        
    # Verify rollback: run_id should NOT be in promoted_runs, since the transaction rolled back
    conn = temp_db._get_conn()
    c = conn.execute("SELECT * FROM promoted_runs WHERE run_id = ?", (run_id,))
    assert c.fetchone() is None
