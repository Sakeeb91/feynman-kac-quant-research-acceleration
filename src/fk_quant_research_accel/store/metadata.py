"""SQLite metadata persistence for batch and scenario runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fk_quant_research_accel.models.result import ScenarioResult

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
        concurrency_limit: int = 1,
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
                artifact_path,
                concurrency_limit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                concurrency_limit,
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

    def update_scenario_status(
        self,
        scenario_run_id: str,
        status: str,
        simulation_id: str | None = None,
        started_at: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE scenario_runs
            SET status = ?, simulation_id = ?, started_at = COALESCE(?, started_at)
            WHERE scenario_run_id = ?
            """,
            (status, simulation_id, started_at, scenario_run_id),
        )
        self.connection.commit()

    def persist_scenario_result(
        self,
        scenario_run_id: str,
        status: str,
        result_json: str,
        score: float | None = None,
        error_message: str | None = None,
        completed_at: str | None = None,
        checkpoint_path: str | None = None,
        scenario_result: ScenarioResult | None = None,
    ) -> None:
        # Keep a typed link from storage layer to scenario result contract.
        _ = scenario_result
        current_row = self.connection.execute(
            "SELECT batch_run_id, status FROM scenario_runs WHERE scenario_run_id = ?",
            (scenario_run_id,),
        ).fetchone()
        self.connection.execute(
            """
            UPDATE scenario_runs
            SET status = ?,
                result_json = ?,
                score = ?,
                error_message = ?,
                completed_at = ?,
                checkpoint_path = ?
            WHERE scenario_run_id = ?
            """,
            (
                status,
                result_json,
                score,
                error_message,
                completed_at,
                checkpoint_path,
                scenario_run_id,
            ),
        )

        if current_row is not None:
            batch_run_id = current_row["batch_run_id"]
            prior_status = current_row["status"]
            if status == "completed" and prior_status != "completed":
                self.connection.execute(
                    """
                    UPDATE batch_runs
                    SET completed_count = completed_count + 1
                    WHERE batch_run_id = ?
                    """,
                    (batch_run_id,),
                )
            elif status == "failed" and prior_status != "failed":
                self.connection.execute(
                    """
                    UPDATE batch_runs
                    SET failed_count = failed_count + 1
                    WHERE batch_run_id = ?
                    """,
                    (batch_run_id,),
                )

        self.connection.commit()

    def update_batch_status(self, batch_run_id: str, status: str) -> None:
        self.connection.execute(
            "UPDATE batch_runs SET status = ? WHERE batch_run_id = ?",
            (status, batch_run_id),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
