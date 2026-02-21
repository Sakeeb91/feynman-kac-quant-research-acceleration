from __future__ import annotations

import json
from datetime import UTC, datetime

from fk_quant_research_accel.models import generate_batch_run_id, generate_scenario_run_id
from fk_quant_research_accel.store.artifacts import ArtifactStore
from fk_quant_research_accel.store.metadata import MetadataStore
from fk_quant_research_accel.store.migrations import init_db


def test_init_db_enables_wal_and_user_version(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    conn = init_db(db_path)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    assert str(journal_mode).lower() == "wal"
    assert user_version == 2


def test_init_db_is_idempotent(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    conn1 = init_db(db_path)
    conn1.close()

    conn2 = init_db(db_path)
    try:
        user_version = conn2.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn2.close()

    assert user_version == 2


def test_metadata_store_batch_roundtrip(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    store = MetadataStore(db_path)
    batch_run_id = str(generate_batch_run_id())

    store.create_batch_run(
        batch_run_id=batch_run_id,
        created_at=datetime.now(UTC).isoformat(),
        config_json=json.dumps({"n_steps": 10}),
        manifest_schema_version=1,
        git_sha="abc123",
        git_dirty=False,
        python_version="3.12.0",
        os_info="test-os",
        seed=123,
        scenario_count=2,
        artifact_path=str(tmp_path / "artifacts" / batch_run_id),
    )
    row = store.get_batch_run(batch_run_id)
    store.close()

    assert row is not None
    assert row["batch_run_id"] == batch_run_id
    assert row["scenario_count"] == 2


def test_metadata_store_scenario_persist_flow(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    store = MetadataStore(db_path)
    batch_run_id = str(generate_batch_run_id())
    scenario_run_id = str(generate_scenario_run_id())

    store.create_batch_run(
        batch_run_id=batch_run_id,
        created_at=datetime.now(UTC).isoformat(),
        config_json="{}",
        manifest_schema_version=1,
        git_sha=None,
        git_dirty=None,
        python_version="3.12.0",
        os_info="test-os",
        seed=None,
        scenario_count=1,
        artifact_path=str(tmp_path / "artifacts" / batch_run_id),
    )
    store.create_scenario_run(
        scenario_run_id=scenario_run_id,
        batch_run_id=batch_run_id,
        scenario_json=json.dumps({"dim": 5}),
        created_at=datetime.now(UTC).isoformat(),
    )
    store.update_scenario_status(
        scenario_run_id=scenario_run_id,
        status="submitted",
        simulation_id="sim-1",
        started_at=datetime.now(UTC).isoformat(),
    )
    store.persist_scenario_result(
        scenario_run_id=scenario_run_id,
        status="completed",
        result_json=json.dumps({"score": 0.1}),
        score=0.1,
        completed_at=datetime.now(UTC).isoformat(),
    )
    scenario_rows = store.get_scenario_runs(batch_run_id)
    batch_row = store.get_batch_run(batch_run_id)
    store.close()

    assert len(scenario_rows) == 1
    assert scenario_rows[0]["status"] == "completed"
    assert batch_row is not None
    assert batch_row["completed_count"] == 1


def test_metadata_store_failed_result_increments_failed_count(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    store = MetadataStore(db_path)
    batch_run_id = str(generate_batch_run_id())
    scenario_run_id = str(generate_scenario_run_id())

    store.create_batch_run(
        batch_run_id=batch_run_id,
        created_at=datetime.now(UTC).isoformat(),
        config_json="{}",
        manifest_schema_version=1,
        git_sha=None,
        git_dirty=None,
        python_version="3.12.0",
        os_info="test-os",
        seed=None,
        scenario_count=1,
        artifact_path=str(tmp_path / "artifacts" / batch_run_id),
    )
    store.create_scenario_run(
        scenario_run_id=scenario_run_id,
        batch_run_id=batch_run_id,
        scenario_json="{}",
        created_at=datetime.now(UTC).isoformat(),
    )
    store.persist_scenario_result(
        scenario_run_id=scenario_run_id,
        status="failed",
        result_json=json.dumps({"status": "failed"}),
        error_message="boom",
        completed_at=datetime.now(UTC).isoformat(),
    )
    scenario_rows = store.get_scenario_runs(batch_run_id)
    batch_row = store.get_batch_run(batch_run_id)
    store.close()

    assert len(scenario_rows) == 1
    assert scenario_rows[0]["status"] == "failed"
    assert scenario_rows[0]["error_message"] == "boom"
    assert batch_row is not None
    assert batch_row["failed_count"] == 1


def test_artifact_store_creates_batch_and_scenario_dirs(tmp_path) -> None:
    artifacts = ArtifactStore(tmp_path / "artifacts")
    batch_run_id = str(generate_batch_run_id())
    scenario_run_id = str(generate_scenario_run_id())

    batch_dir = artifacts.create_batch_dir(batch_run_id)
    scenario_dir = artifacts.create_scenario_dir(batch_run_id, scenario_run_id)

    assert batch_dir.exists()
    assert scenario_dir.exists()
    assert artifacts.get_scenario_dir(batch_run_id, scenario_run_id) == scenario_dir


def test_artifact_store_atomic_write_json_and_text_and_bytes(tmp_path) -> None:
    artifacts = ArtifactStore(tmp_path / "artifacts")
    batch_run_id = str(generate_batch_run_id())
    scenario_run_id = str(generate_scenario_run_id())
    scenario_dir = artifacts.create_scenario_dir(batch_run_id, scenario_run_id)

    json_path = scenario_dir / "result.json"
    text_path = scenario_dir / "notes.txt"
    bytes_path = scenario_dir / "checkpoint.bin"

    artifacts.atomic_write_json(json_path, {"score": 0.1, "status": "completed"})
    artifacts.atomic_write_text(text_path, "hello")
    artifacts.atomic_write_bytes(bytes_path, b"abc")

    with json_path.open("r", encoding="utf-8") as handle:
        parsed = json.load(handle)

    assert parsed["status"] == "completed"
    assert text_path.read_text(encoding="utf-8") == "hello"
    assert bytes_path.read_bytes() == b"abc"
