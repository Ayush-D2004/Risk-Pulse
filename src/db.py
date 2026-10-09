import sqlite3
import os
import json
import threading
from typing import Optional

# Determine DB path dynamically, default to "data/riskpulse_runtime.db" in the project root
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "riskpulse_runtime.db")

class DatabaseLayer:
    """
    A minimal, durable SQLite persistence layer for pipeline runs and promoted events.
    Thread-local connections are used to ensure safe concurrency when called from asyncio.to_thread
    or FastAPI worker threads.
    """
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        
        # Initialize schema if missing
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            # timeout=30 helps prevent "database is locked" during concurrent promotions
            self._local.conn = sqlite3.connect(self.db_path, timeout=30)
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency and foreign keys for referential integrity
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_schema(self):
        conn = self._get_conn()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS promoted_runs (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    source TEXT,
                    channel TEXT,
                    promoted_at REAL NOT NULL,
                    event_ids_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS promoted_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    signal_payload TEXT NOT NULL,
                    result_payload TEXT NOT NULL,
                    provenance TEXT,
                    FOREIGN KEY(run_id) REFERENCES promoted_runs(run_id) ON DELETE CASCADE
                )
            """)
            
            # Phase 3G.2: Tables for GDELT continuous ingestion worker
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingested_articles (
                    doc_id TEXT PRIMARY KEY,
                    fetched_at REAL NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gdelt_worker_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_attempt_at REAL,
                    last_success_at REAL,
                    last_result_category TEXT,
                    fetched_count INTEGER DEFAULT 0,
                    deduped_count INTEGER DEFAULT 0,
                    submitted_count INTEGER DEFAULT 0,
                    active_run_id TEXT
                )
            """)
            # Ensure the single row exists
            conn.execute("INSERT OR IGNORE INTO gdelt_worker_status (id) VALUES (1)")

            
            # Indexes for querying runs chronologically or by status
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON pipeline_runs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created_at ON pipeline_runs(created_at DESC)")

db_instance = DatabaseLayer()
