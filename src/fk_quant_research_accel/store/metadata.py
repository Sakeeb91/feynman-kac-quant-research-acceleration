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

    def list_batch_runs(
        self,
        *,
        status: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        git_sha: str | None = None,
        manifest_hash: str | None = None,
        order_by: str = "created_at DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        allowed_order_by = {"created_at DESC", "created_at ASC"}
        effective_order_by = order_by if order_by in allowed_order_by else "created_at DESC"
        where_clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            where_clauses.append("b.status = ?")
            params.append(status)
        if from_date is not None:
            where_clauses.append("b.created_at >= ?")
            params.append(from_date)
        if to_date is not None:
            where_clauses.append("b.created_at <= ?")
            params.append(to_date)
        if git_sha is not None:
            where_clauses.append("b.git_sha = ?")
            params.append(git_sha)
        if manifest_hash is not None:
            where_clauses.append("b.manifest_hash = ?")
            params.append(manifest_hash)
        where_sql = ""
        if where_clauses:
            where_sql = f"WHERE {' AND '.join(where_clauses)}"
        rows = self.connection.execute(
            f"""
            SELECT
                b.*,
                MIN(CASE WHEN s.status = 'completed' THEN s.score END) AS best_score
            FROM batch_runs AS b
            LEFT JOIN scenario_runs AS s ON s.batch_run_id = b.batch_run_id
            {where_sql}
            GROUP BY b.batch_run_id
            ORDER BY b.{effective_order_by}
            LIMIT ?
            OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_scenario_runs(self, batch_run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM scenario_runs WHERE batch_run_id = ?",
            (batch_run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_incomplete_scenario_runs(self, batch_run_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM scenario_runs
            WHERE batch_run_id = ?
              AND status NOT IN ('completed', 'failed', 'cancelled')
            """,
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

    def update_batch_interrupted(self, batch_run_id: str, interrupted_at: str) -> None:
        self.connection.execute(
            """
            UPDATE batch_runs
            SET status = 'interrupted', interrupted_at = ?
            WHERE batch_run_id = ?
            """,
            (interrupted_at, batch_run_id),
        )
        self.connection.commit()

    def update_scenario_retry_count(self, scenario_run_id: str, retry_count: int) -> None:
        self.connection.execute(
            """
            UPDATE scenario_runs
            SET retry_count = ?
            WHERE scenario_run_id = ?
            """,
            (retry_count, scenario_run_id),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
