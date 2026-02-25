"""SQLite schema setup and migration management."""

from __future__ import annotations

import sqlite3
from pathlib import Path


CURRENT_SCHEMA_VERSION = 4


def init_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Async orchestration performs DB work in worker threads via anyio.to_thread.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row

    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    _apply_migrations(conn, current_version)
    return conn


def _apply_migrations(conn: sqlite3.Connection, current_version: int) -> None:
    migrations = {
        0: _migrate_v0_to_v1,
        1: _migrate_v1_to_v2,
        2: _migrate_v2_to_v3,
    }
    for version in range(current_version, CURRENT_SCHEMA_VERSION):
        migration = migrations.get(version)
        if migration is None:
            raise ValueError(f"Missing migration from v{version}")
        migration(conn)
        conn.execute(f"PRAGMA user_version = {version + 1}")
        conn.commit()


def _migrate_v0_to_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS batch_runs (
            batch_run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            config_json TEXT NOT NULL,
            manifest_schema_version INTEGER NOT NULL DEFAULT 1,
            git_sha TEXT,
            git_dirty INTEGER,
            python_version TEXT,
            os_info TEXT,
            seed INTEGER,
            scenario_count INTEGER NOT NULL,
            completed_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            artifact_path TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scenario_runs (
            scenario_run_id TEXT PRIMARY KEY,
            batch_run_id TEXT NOT NULL REFERENCES batch_runs(batch_run_id),
            scenario_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            simulation_id TEXT,
            result_json TEXT,
            score REAL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            checkpoint_path TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scenario_batch ON scenario_runs(batch_run_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scenario_status ON scenario_runs(status)"
    )


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """Add retry and concurrency metadata columns for Phase 3."""
    conn.execute("ALTER TABLE scenario_runs ADD COLUMN retry_count INTEGER DEFAULT 0")
    conn.execute("ALTER TABLE scenario_runs ADD COLUMN max_retries INTEGER DEFAULT 3")
    conn.execute("ALTER TABLE batch_runs ADD COLUMN concurrency_limit INTEGER DEFAULT 1")
    conn.execute("ALTER TABLE batch_runs ADD COLUMN interrupted_at TEXT")


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """Add manifest hash metadata column for run analysis filtering."""
    conn.execute("ALTER TABLE batch_runs ADD COLUMN manifest_hash TEXT")


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Add problem_id metadata column for extensible problem dispatch."""
    conn.execute(
        "ALTER TABLE batch_runs ADD COLUMN problem_id TEXT DEFAULT 'black_scholes'"
    )
