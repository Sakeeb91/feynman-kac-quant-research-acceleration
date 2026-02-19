"""SQLite metadata persistence for batch and scenario runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .migrations import init_db


class MetadataStore:
    def __init__(self, db_path: str | Path) -> None:
        self.connection = init_db(db_path)

    def create_batch_run(
        self,
        batch_run_id: str,
        created_at: str,
        config_json: str,
        manifest_schema_version: int,
        git_sha: str | None,
        git_dirty: bool | None,
        python_version: str,
        os_info: str,
        seed: int | None,
        scenario_count: int,
        artifact_path: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO batch_runs (
                batch_run_id,
                created_at,
                config_json,
                manifest_schema_version,
                git_sha,
                git_dirty,
                python_version,
                os_info,
                seed,
                scenario_count,
                artifact_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_run_id,
                created_at,
                config_json,
                manifest_schema_version,
                git_sha,
                None if git_dirty is None else int(git_dirty),
                python_version,
                os_info,
                seed,
                scenario_count,
                artifact_path,
            ),
        )
        self.connection.commit()

    def create_scenario_run(
        self,
        scenario_run_id: str,
        batch_run_id: str,
        scenario_json: str,
        created_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO scenario_runs (
                scenario_run_id,
                batch_run_id,
                scenario_json,
                status,
                created_at
            ) VALUES (?, ?, ?, 'pending', ?)
            """,
            (scenario_run_id, batch_run_id, scenario_json, created_at),
        )
        self.connection.commit()

    def get_batch_run(self, batch_run_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM batch_runs WHERE batch_run_id = ?",
            (batch_run_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_scenario_runs(self, batch_run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM scenario_runs WHERE batch_run_id = ?",
            (batch_run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_batch_status(self, batch_run_id: str, status: str) -> None:
        self.connection.execute(
            "UPDATE batch_runs SET status = ? WHERE batch_run_id = ?",
            (status, batch_run_id),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
