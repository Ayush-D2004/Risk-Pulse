import pytest
import asyncio
import time
import requests
import sqlite3
from unittest.mock import MagicMock, AsyncMock, patch
from src.ingestion.worker import GDELTWorker, GDELTWorkerConfig
from src.ingestion.gdelt_client import GDELTClient
from src.integration.gdelt_service import GDELTIntegrationService
from src.db import DatabaseLayer

@pytest.fixture
def mock_db(tmp_path):
    db_path = tmp_path / "test_runtime.db"
    return DatabaseLayer(str(db_path))

@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock()
    orchestrator.process_run = AsyncMock()
    return orchestrator

@pytest.fixture
def gdelt_service(mock_db, mock_orchestrator):
    store = MagicMock()
    store.add_run = MagicMock()
    client = GDELTClient()
    service = GDELTIntegrationService(mock_orchestrator, store, client)
    # mock client normalization slightly to avoid hitting real hashlib if needed, but it works offline
    return service

@pytest.fixture
def mock_response():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    return resp

def test_successful_retrieval(gdelt_service, mock_db):
    config = GDELTWorkerConfig(enabled=True, polling_interval_seconds=1)
    worker = GDELTWorker(gdelt_service, config, db=mock_db)
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "articles": [
                {"url": "http://test1.com", "title": "Cyberattack!", "seendate": "20231015093000Z"}
            ]
        }
        mock_get.return_value = mock_resp
        
        async def run_one_cycle():
            worker.start()
            await asyncio.sleep(0.1)
            worker.stop()
            if worker._task:
                await worker._task

        asyncio.run(run_one_cycle())
        
        # Verify run was added
        gdelt_service.store.add_run.assert_called_once()
        run = gdelt_service.store.add_run.call_args[0][0]
        assert run.request.observations[0].url == "http://test1.com"
        assert run.request.mode.value == "LIVE_GDELT"
        
        # Verify db status
        conn = mock_db._get_conn()
        row = conn.execute("SELECT * FROM gdelt_worker_status").fetchone()
        assert row["last_result_category"] == "success"
        assert row["fetched_count"] == 1
        assert row["deduped_count"] == 0
        assert row["submitted_count"] == 1
        
def test_successful_retrieval_zero_obs(gdelt_service, mock_db):
    config = GDELTWorkerConfig(enabled=True, polling_interval_seconds=1)
    worker = GDELTWorker(gdelt_service, config, db=mock_db)
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"articles": []}
        mock_get.return_value = mock_resp
        
        async def run_one_cycle():
            worker.start()
            await asyncio.sleep(0.1)
            task = worker._task
            worker.stop()
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        asyncio.run(run_one_cycle())
        
        gdelt_service.store.add_run.assert_not_called()
        
        conn = mock_db._get_conn()
        row = conn.execute("SELECT * FROM gdelt_worker_status").fetchone()
        assert row["last_result_category"] == "empty"

def test_deduplication_across_polls(gdelt_service, mock_db):
    config = GDELTWorkerConfig(enabled=True, polling_interval_seconds=1)
    worker = GDELTWorker(gdelt_service, config, db=mock_db)
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "articles": [
                {"url": "http://test1.com", "title": "Cyberattack!", "seendate": "20231015093000Z"}
            ]
        }
        mock_get.return_value = mock_resp
        
        # First poll
        async def run_cycle():
            worker.start()
            await asyncio.sleep(0.1)
            task = worker._task
            worker.stop()
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        asyncio.run(run_cycle())
        assert gdelt_service.store.add_run.call_count == 1
        
        # Second poll identical
        asyncio.run(run_cycle())
        assert gdelt_service.store.add_run.call_count == 1 # still 1!
        
        conn = mock_db._get_conn()
        row = conn.execute("SELECT * FROM gdelt_worker_status").fetchone()
        assert row["last_result_category"] == "success"
        assert row["fetched_count"] == 1
        assert row["deduped_count"] == 1
        assert row["submitted_count"] == 0

def test_http_429_with_retry_after(gdelt_service, mock_db):
    config = GDELTWorkerConfig(enabled=True, polling_interval_seconds=1)
    worker = GDELTWorker(gdelt_service, config, db=mock_db)
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "42"}
        err = requests.exceptions.HTTPError()
        err.response = mock_resp
        mock_get.side_effect = err
        
        async def run_cycle():
            worker.start()
            await asyncio.sleep(0.1)
            task = worker._task
            worker.stop()
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                
        asyncio.run(run_cycle())
        
        gdelt_service.store.add_run.assert_not_called()
        
        conn = mock_db._get_conn()
        row = conn.execute("SELECT * FROM gdelt_worker_status").fetchone()
        assert row["last_result_category"] == "rate_limited"
        # Since sleep uses sleep(1) chunks internally in _sleep, it cleanly cancels. 
        # But we would normally test current_sleep updated to 42, which is an internal var.

def test_graceful_shutdown(gdelt_service, mock_db):
    config = GDELTWorkerConfig(enabled=True, polling_interval_seconds=300)
    worker = GDELTWorker(gdelt_service, config, db=mock_db)
    
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"articles": []}
        
        async def run_and_stop():
            worker.start()
            await asyncio.sleep(0.1)
            assert worker._task is not None
            assert not worker._task.done()
            task = worker._task
            worker.stop()
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
        asyncio.run(run_and_stop())
        assert worker._task is None
