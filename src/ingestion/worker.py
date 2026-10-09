import asyncio
import time
from typing import Optional, List
import requests

from src.ingestion.gdelt_client import GDELTClient
from src.integration.gdelt_service import GDELTIntegrationService
from src.db import DatabaseLayer, db_instance
from src.integration.observation_adapter import adapt_gdelt_to_run_request
from src.integration.runtime_models import PipelineRun
import uuid

class GDELTWorkerConfig:
    def __init__(
        self,
        enabled: bool = False,
        polling_interval_seconds: int = 300,
        query: str = "cyberattack OR hack",
        max_records: int = 5,
        timeout: int = 30,
        max_concurrent_runs: int = 1
    ):
        self.enabled = enabled
        self.polling_interval_seconds = polling_interval_seconds
        self.query = query
        self.max_records = max_records
        self.timeout = timeout
        self.max_concurrent_runs = max_concurrent_runs


class GDELTWorker:
    def __init__(
        self, 
        gdelt_service: GDELTIntegrationService, 
        config: GDELTWorkerConfig,
        db: DatabaseLayer = db_instance
    ):
        self.gdelt_service = gdelt_service
        self.config = config
        self.db = db
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def _update_status(
        self, 
        last_attempt: float, 
        last_success: Optional[float] = None, 
        category: str = "",
        fetched: int = 0,
        deduped: int = 0,
        submitted: int = 0,
        active_run_id: Optional[str] = None
    ):
        conn = self.db._get_conn()
        with conn:
            # We fetch existing to preserve values if not explicitly updating
            row = conn.execute("SELECT * FROM gdelt_worker_status WHERE id = 1").fetchone()
            new_success = last_success if last_success is not None else row["last_success_at"]
            conn.execute("""
                UPDATE gdelt_worker_status 
                SET last_attempt_at = ?, last_success_at = ?, last_result_category = ?,
                    fetched_count = ?, deduped_count = ?, submitted_count = ?, active_run_id = ?
                WHERE id = 1
            """, (last_attempt, new_success, category, fetched, deduped, submitted, active_run_id))

    def _is_deduped(self, doc_id: str) -> bool:
        conn = self.db._get_conn()
        row = conn.execute("SELECT 1 FROM ingested_articles WHERE doc_id = ?", (doc_id,)).fetchone()
        return row is not None

    def _mark_ingested(self, doc_id: str, fetched_at: float):
        conn = self.db._get_conn()
        with conn:
            conn.execute("INSERT OR IGNORE INTO ingested_articles (doc_id, fetched_at) VALUES (?, ?)", (doc_id, fetched_at))

    def start(self):
        if not self.config.enabled:
            return
        if self._task is None:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop())

    def stop(self):
        if self._task:
            self._stop_event.set()
            self._task.cancel()
            self._task = None

    async def _run_loop(self):
        # We start with the configured polling interval
        current_sleep = self.config.polling_interval_seconds
        while not self._stop_event.is_set():
            attempt_time = time.time()
            try:
                # 1. Fetch raw
                raw_articles = await asyncio.to_thread(
                    self.gdelt_service.gdelt_client.fetch_live, 
                    self.config.query, 
                    self.config.max_records
                )
                
                fetched_count = len(raw_articles) if raw_articles else 0
                if fetched_count == 0:
                    self._update_status(attempt_time, last_success=attempt_time, category="empty")
                    await self._sleep(current_sleep)
                    continue
                
                # 2. Normalize & deduplicate
                docs = self.gdelt_service.gdelt_client.normalize(raw_articles)
                new_docs = []
                for d in docs:
                    if not self._is_deduped(d.document_id):
                        new_docs.append(d)
                        self._mark_ingested(d.document_id, attempt_time)

                deduped_count = len(docs) - len(new_docs)
                submitted_count = len(new_docs)

                if submitted_count == 0:
                    self._update_status(
                        attempt_time, last_success=attempt_time, category="success", 
                        fetched=fetched_count, deduped=deduped_count, submitted=0
                    )
                    await self._sleep(current_sleep)
                    continue

                # 3. Create run
                req = adapt_gdelt_to_run_request(new_docs)
                run_id = uuid.uuid4().hex
                run = PipelineRun(run_id=run_id, request=req)
                self.gdelt_service.store.add_run(run)
                
                self._update_status(
                    attempt_time, last_success=attempt_time, category="success",
                    fetched=fetched_count, deduped=deduped_count, submitted=submitted_count, active_run_id=run_id
                )

                # 4. Process run via orchestrator (await it or fire-and-forget based on concurrency constraints)
                # We enforce max_concurrent_runs=1 by awaiting the run processing.
                await self.gdelt_service.orchestrator.process_run(run)
                
                # Clear active_run_id after completion
                self._update_status(
                    time.time(), category="success", 
                    fetched=fetched_count, deduped=deduped_count, submitted=submitted_count, active_run_id=None
                )
                
                # Reset sleep on success
                current_sleep = self.config.polling_interval_seconds
                
            except requests.exceptions.HTTPError as e:
                resp = e.response
                if resp is not None and resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        current_sleep = int(retry_after)
                    else:
                        current_sleep = min(current_sleep * 2, 3600) # exponential backoff capped at 1h
                    self._update_status(attempt_time, category="rate_limited")
                else:
                    self._update_status(attempt_time, category="error")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._update_status(attempt_time, category="failed")
                current_sleep = min(current_sleep * 2, 3600)
                
            await self._sleep(current_sleep)

    async def _sleep(self, seconds: float):
        try:
            # We wait with a short timeout loop so we can exit fast on stop_event
            end_time = time.time() + seconds
            while time.time() < end_time:
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
