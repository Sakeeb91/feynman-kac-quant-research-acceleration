from __future__ import annotations

import json
from typing import Any
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import fk_quant_research_accel.cli as cli_module
from fk_quant_research_accel.cli import app
from fk_quant_research_accel.store.metadata import MetadataStore
from fk_quant_research_accel.validation import PreflightError


runner = CliRunner()


def _ok_rows() -> list[dict[str, Any]]:
    return [
        {
            "score": 0.1,
            "convergence_health": "healthy",
            "dim": 5,
            "volatility": 0.2,
            "correlation": 0.0,
            "option_type": "call",
            "status": "completed",
            "train_loss": 0.1,
            "progress": 1.0,
            "val_loss": None,
            "lr": 1e-3,
            "grad_norm": 0.1,
            "error_message": None,
            "checkpoint_path": None,
            "simulation_id": "sim-1",
        }
    ]


def _patch_anyio_run_capture(monkeypatch, *, returned_rows: list[dict[str, Any]] | None = None):
    captured: dict[str, Any] = {}

    def fake_anyio_run(callable_obj):
        captured["callable"] = callable_obj
        if returned_rows is not None:
            return returned_rows
        return _ok_rows()

    monkeypatch.setattr(cli_module.anyio, "run", fake_anyio_run)
    return captured


def _patch_render_leaderboard_capture(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {"calls": []}

    def fake_render_leaderboard(rows, n=10, title="Leaderboard", console=None):
        captured["calls"].append(
            {
                "rows": rows,
                "n": n,
                "title": title,
                "console": console,
            }
        )

    monkeypatch.setattr(cli_module, "render_leaderboard", fake_render_leaderboard)
    return captured


def _write_manifest(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return path


def _insert_listing_batch(
    store: MetadataStore,
    *,
    batch_run_id: str,
    created_at: str,
    status: str = "completed",
    git_sha: str | None = None,
) -> None:
    store.create_batch_run(
        batch_run_id=batch_run_id,
        created_at=created_at,
        config_json=json.dumps({"n_steps": 10}),
        manifest_schema_version=1,
        git_sha=git_sha,
        git_dirty=False,
        python_version="3.12.0",
        os_info="test-os",
        seed=123,
        scenario_count=1,
        artifact_path=f"/tmp/{batch_run_id}",
        manifest_hash="manifest-abc",
    )
    store.update_batch_status(batch_run_id, status)


def _insert_listing_scenario(store: MetadataStore, *, batch_run_id: str, score: float) -> None:
    scenario_run_id = f"scenario-{batch_run_id}-{score}"
    store.create_scenario_run(
        scenario_run_id=scenario_run_id,
        batch_run_id=batch_run_id,
        scenario_json=json.dumps({"dim": 5}),
        created_at="2025-01-01T00:00:00+00:00",
    )
    store.persist_scenario_result(
        scenario_run_id=scenario_run_id,
        status="completed",
        result_json=json.dumps({"status": "completed", "score": score}),
        score=score,
        completed_at="2025-01-01T00:01:00+00:00",
    )


def _insert_compare_scenario(
    store: MetadataStore,
    *,
    batch_run_id: str,
    scenario_run_id: str,
    scenario_payload: dict[str, object],
    status: str,
    score: float | None,
    train_loss: float | None = None,
    grad_norm: float | None = None,
    progress: float | None = None,
) -> None:
    store.create_scenario_run(
        scenario_run_id=scenario_run_id,
        batch_run_id=batch_run_id,
        scenario_json=json.dumps(scenario_payload),
        created_at="2025-01-01T00:00:00+00:00",
    )
    store.persist_scenario_result(
        scenario_run_id=scenario_run_id,
        status=status,
        result_json=json.dumps(
            {
                "status": status,
                "score": score,
                "train_loss": train_loss,
                "grad_norm": grad_norm,
                "progress": progress,
                "convergence_health": "healthy" if status == "completed" else "exploding",
            }
        ),
        score=score,
        error_message="failed" if status == "failed" else None,
        checkpoint_path="/tmp/checkpoint.pt" if status == "completed" else None,
        completed_at="2025-01-01T00:01:00+00:00",
    )


@pytest.fixture
def populated_db(tmp_path) -> str:
    db_path = tmp_path / "experiments.db"
    store = MetadataStore(db_path)
    _insert_listing_batch(
        store,
        batch_run_id="aaaaaaaa-1111-1111-1111-111111111111",
        created_at="2025-01-01T00:00:00+00:00",
        status="completed",
        git_sha="abc123",
    )
    _insert_listing_batch(
        store,
        batch_run_id="bbbbbbbb-2222-2222-2222-222222222222",
        created_at="2025-01-02T00:00:00+00:00",
        status="running",
        git_sha="def456",
    )
    _insert_listing_scenario(
        store,
        batch_run_id="aaaaaaaa-1111-1111-1111-111111111111",
        score=0.1,
    )
    _insert_listing_scenario(
        store,
        batch_run_id="bbbbbbbb-2222-2222-2222-222222222222",
        score=0.3,
    )
    store.close()
    return str(db_path)


@pytest.fixture
def compare_db(tmp_path) -> tuple[str, str, str]:
    db_path = tmp_path / "compare.db"
    run_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    run_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    store = MetadataStore(db_path)
    _insert_listing_batch(
        store,
        batch_run_id=run_a,
        created_at="2025-01-01T00:00:00+00:00",
        status="completed",
    )
    _insert_listing_batch(
        store,
        batch_run_id=run_b,
        created_at="2025-01-02T00:00:00+00:00",
        status="completed",
    )

    shared_1 = {"dim": 5, "volatility": 0.2, "correlation": 0.0, "option_type": "call"}
    shared_2 = {"dim": 10, "volatility": 0.3, "correlation": 0.1, "option_type": "call"}
    only_a = {"dim": 15, "volatility": 0.4, "correlation": 0.2, "option_type": "put"}
    only_b = {"dim": 20, "volatility": 0.5, "correlation": 0.3, "option_type": "put"}

    _insert_compare_scenario(
        store,
        batch_run_id=run_a,
        scenario_run_id="a-1",
        scenario_payload=shared_1,
        status="completed",
        score=0.1,
        train_loss=0.1,
        grad_norm=0.2,
        progress=1.0,
    )
    _insert_compare_scenario(
        store,
        batch_run_id=run_b,
        scenario_run_id="b-1",
        scenario_payload=shared_1,
        status="completed",
        score=0.2,
        train_loss=0.2,
        grad_norm=0.3,
        progress=1.0,
    )
    _insert_compare_scenario(
        store,
        batch_run_id=run_a,
        scenario_run_id="a-2",
        scenario_payload=shared_2,
        status="completed",
        score=0.3,
        train_loss=0.3,
        grad_norm=0.4,
        progress=0.9,
    )
    _insert_compare_scenario(
        store,
        batch_run_id=run_b,
        scenario_run_id="b-2",
        scenario_payload=shared_2,
        status="completed",
        score=0.25,
        train_loss=0.25,
        grad_norm=0.35,
        progress=0.95,
    )
    _insert_compare_scenario(
        store,
        batch_run_id=run_a,
        scenario_run_id="a-3",
        scenario_payload=only_a,
        status="completed",
        score=0.4,
    )
    _insert_compare_scenario(
        store,
        batch_run_id=run_b,
        scenario_run_id="b-3",
        scenario_payload=only_b,
        status="completed",
        score=0.35,
    )
    store.close()
    return str(db_path), run_a, run_b


@pytest.fixture
def compare_db_mixed_status(tmp_path) -> tuple[str, str, str]:
    db_path = tmp_path / "compare-mixed.db"
    run_a = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    run_b = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    store = MetadataStore(db_path)
    _insert_listing_batch(store, batch_run_id=run_a, created_at="2025-01-01T00:00:00+00:00")
    _insert_listing_batch(store, batch_run_id=run_b, created_at="2025-01-02T00:00:00+00:00")

    scenario = {"dim": 5, "volatility": 0.2, "correlation": 0.0, "option_type": "call"}
    _insert_compare_scenario(
        store,
        batch_run_id=run_a,
        scenario_run_id="ca-1",
        scenario_payload=scenario,
        status="failed",
        score=None,
    )
    _insert_compare_scenario(
        store,
        batch_run_id=run_b,
        scenario_run_id="db-1",
        scenario_payload=scenario,
        status="completed",
        score=0.2,
    )
    store.close()
    return str(db_path), run_a, run_b


def test_help_includes_program_name_and_log_level() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "fk-research" in result.stdout
    assert "--log-level" in result.stdout
    assert "run-batch" in result.stdout
    assert "resume-batch" in result.stdout


def test_run_batch_help_includes_expected_flags() -> None:
    result = runner.invoke(app, ["run-batch", "--help"])
    assert result.exit_code == 0
    for flag in [
        "--base-url",
        "--dimensions",
        "--volatilities",
        "--correlations",
        "--option-types",
        "--n-steps",
        "--batch-size",
        "--n-mc-paths",
        "--learning-rate",
        "--poll-seconds",
        "--max-wait-seconds",
        "--concurrency",
        "--max-retries",
        "--output",
        "--manifest",
    ]:
        assert flag in result.stdout


def test_cli_manifest_option_exists_in_help() -> None:
    result = runner.invoke(app, ["run-batch", "--help"])

    assert result.exit_code == 0
    assert "--manifest" in result.stdout


def test_resume_batch_help() -> None:
    result = runner.invoke(app, ["resume-batch", "--help"])

    assert result.exit_code == 0
    for flag in [
        "--base-url",
        "--force",
        "--concurrency",
        "--max-retries",
        "--poll-seconds",
        "--max-wait-seconds",
        "--db-path",
        "--artifacts-dir",
        "--output",
    ]:
        assert flag in result.stdout


def test_cli_manifest_loads_and_validates(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())

    manifest_path = _write_manifest(
        tmp_path / "experiment.yaml",
        {
            "backend_url": "http://manifest-backend:9000",
            "seed": 123,
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
            "batch_config": {
                "n_steps": 50,
                "batch_size": 32,
                "n_mc_paths": 128,
                "learning_rate": 0.0005,
            },
            "output": {
                "artifacts_dir": str(tmp_path / "artifacts"),
                "db_path": str(tmp_path / "custom.db"),
            },
            "scoring": {
                "strategy": "convergence_rate",
            },
        },
    )

    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        ["run-batch", "--manifest", str(manifest_path), "--output", str(tmp_path / "out.csv")],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.func == cli_module.run_batch_async
    assert call.keywords["client"].base_url == "http://manifest-backend:9000"
    assert call.keywords["experiment_manifest_hash"] is not None
    assert call.keywords["seed"] == 123
    assert str(call.keywords["artifacts_dir"]).endswith("artifacts")
    assert call.keywords["scoring_config"].strategy.value == "convergence_rate"


def test_run_batch_manifest_uses_async(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())
    manifest_path = _write_manifest(
        tmp_path / "experiment.yaml",
        {
            "backend_url": "http://manifest-backend:9000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
        },
    )

    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--manifest",
            str(manifest_path),
            "--concurrency",
            "10",
            "--max-retries",
            "2",
        ],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.func == cli_module.run_batch_async
    assert call.keywords["concurrency_limit"] == 10
    assert call.keywords["max_retries"] == 2


def test_cli_manifest_preflight_fails_exits_1(monkeypatch, tmp_path) -> None:
    called = {"anyio_run": False}

    def fake_anyio_run(callable_obj):
        called["anyio_run"] = True
        del callable_obj
        return _ok_rows()

    manifest_path = _write_manifest(
        tmp_path / "invalid.yaml",
        {
            "backend_url": "http://manifest-backend:9000",
            "scenario_grid": {
                "dimensions": [3],
                "volatilities": [0.2],
                "correlations": [[1.0, 0.5], [0.5, 1.0]],
                "option_types": ["call"],
            },
        },
    )

    monkeypatch.setattr(cli_module.anyio, "run", fake_anyio_run)
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(app, ["run-batch", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert called["anyio_run"] is False


def test_run_batch_manifest_preflight_still_works(monkeypatch, tmp_path) -> None:
    called = {"anyio_run": False}

    def fake_anyio_run(callable_obj):
        called["anyio_run"] = True
        del callable_obj
        return _ok_rows()

    manifest_path = _write_manifest(
        tmp_path / "manifest.yaml",
        {
            "backend_url": "http://manifest-backend:9000",
            "scenario_grid": {
                "dimensions": [3],
                "volatilities": [0.2],
                "correlations": [[1.0, 0.5], [0.5, 1.0]],
                "option_types": ["call"],
            },
        },
    )

    monkeypatch.setattr(cli_module.anyio, "run", fake_anyio_run)
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(app, ["run-batch", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert called["anyio_run"] is False


def test_cli_backward_compat_flags(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())

    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--base-url",
            "http://legacy-backend:8000",
            "--dimensions",
            "5",
            "--volatilities",
            "0.2",
            "--correlations",
            "0.0",
            "--option-types",
            "call",
            "--output",
            str(tmp_path / "legacy.csv"),
        ],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.func == cli_module.run_batch_async
    assert call.keywords["client"].base_url == "http://legacy-backend:8000"


def test_run_batch_legacy_flags_uses_async(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--base-url",
            "http://legacy-backend:8000",
            "--dimensions",
            "5",
            "--volatilities",
            "0.2",
            "--correlations",
            "0.0",
            "--option-types",
            "call",
            "--concurrency",
            "5",
            "--output",
            str(tmp_path / "legacy-async.csv"),
        ],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.func == cli_module.run_batch_async
    assert call.keywords["concurrency_limit"] == 5


def test_cli_base_url_required_without_manifest() -> None:
    result = runner.invoke(app, ["run-batch"])

    assert result.exit_code != 0
    assert "--base-url is required when --manifest is not provided" in result.output


def test_run_batch_default_concurrency(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--base-url",
            "http://legacy-backend:8000",
            "--dimensions",
            "5",
            "--volatilities",
            "0.2",
            "--correlations",
            "0.0",
            "--option-types",
            "call",
            "--output",
            str(tmp_path / "default-concurrency.csv"),
        ],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.keywords["concurrency_limit"] == 20


def test_run_batch_default_max_retries(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--base-url",
            "http://legacy-backend:8000",
            "--dimensions",
            "5",
            "--volatilities",
            "0.2",
            "--correlations",
            "0.0",
            "--option-types",
            "call",
            "--output",
            str(tmp_path / "default-retries.csv"),
        ],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.keywords["max_retries"] == 3


def test_cli_manifest_overrides_legacy_flags(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())

    manifest_path = _write_manifest(
        tmp_path / "experiment.yaml",
        {
            "backend_url": "http://manifest-backend:9000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
        },
    )

    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--manifest",
            str(manifest_path),
            "--base-url",
            "http://ignored-base-url:7000",
            "--dimensions",
            "99",
            "--volatilities",
            "4.2",
            "--correlations",
            "0.9",
        ],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.keywords["client"].base_url == "http://manifest-backend:9000"
    assert len(call.keywords["scenarios"]) == 1


def test_cli_manifest_load_failure_exits_1(monkeypatch, tmp_path) -> None:
    called = {"anyio_run": False}

    def fake_anyio_run(callable_obj):
        called["anyio_run"] = True
        del callable_obj
        return _ok_rows()

    manifest_path = tmp_path / "broken.yaml"
    manifest_path.write_text("backend_url: [unclosed", encoding="utf-8")

    monkeypatch.setattr(cli_module.anyio, "run", fake_anyio_run)
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(app, ["run-batch", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert called["anyio_run"] is False


def test_cli_manifest_preflight_logs_all_errors(monkeypatch, tmp_path) -> None:
    called = {"anyio_run": False}

    def fake_anyio_run(callable_obj):
        called["anyio_run"] = True
        del callable_obj
        return _ok_rows()

    manifest_path = _write_manifest(
        tmp_path / "experiment.yaml",
        {
            "backend_url": "http://manifest-backend:9000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
        },
    )

    monkeypatch.setattr(cli_module.anyio, "run", fake_anyio_run)
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))
    monkeypatch.setattr(
        cli_module,
        "validate_manifest",
        lambda manifest: [
            PreflightError(field="field.one", value=1, message="first error"),
            PreflightError(field="field.two", value=2, message="second error"),
        ],
    )

    result = runner.invoke(app, ["run-batch", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert result.output.count("preflight_validation_failed") >= 2
    assert called["anyio_run"] is False


def test_resume_batch_invocation(monkeypatch, tmp_path) -> None:
    captured = _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "resume-batch",
            "BATCH123",
            "--base-url",
            "http://test:8000",
            "--force",
            "--concurrency",
            "10",
            "--max-retries",
            "4",
            "--db-path",
            str(tmp_path / "exp.db"),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ],
    )

    assert result.exit_code == 0
    call = captured["callable"]
    assert call.func == cli_module.resume_batch_async
    assert call.keywords["batch_run_id"] == "BATCH123"
    assert call.keywords["force"] is True
    assert call.keywords["concurrency_limit"] == 10
    assert call.keywords["max_retries"] == 4


def test_resume_batch_nonexistent_batch(monkeypatch) -> None:
    def fake_anyio_run(callable_obj):
        del callable_obj
        raise ValueError("Batch not found")

    monkeypatch.setattr(cli_module.anyio, "run", fake_anyio_run)
    _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "resume-batch",
            "NONEXISTENT",
            "--base-url",
            "http://test:8000",
        ],
    )

    assert result.exit_code == 1
    assert "resume_batch_failed" in result.output


def test_run_batch_invokes_render_leaderboard(monkeypatch, tmp_path) -> None:
    _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())
    rendered = _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "run-batch",
            "--base-url",
            "http://legacy-backend:8000",
            "--dimensions",
            "5",
            "--volatilities",
            "0.2",
            "--correlations",
            "0.0",
            "--option-types",
            "call",
            "--output",
            str(tmp_path / "legacy.csv"),
        ],
    )

    assert result.exit_code == 0
    assert len(rendered["calls"]) == 1


def test_resume_batch_invokes_render_leaderboard(monkeypatch, tmp_path) -> None:
    _patch_anyio_run_capture(monkeypatch, returned_rows=_ok_rows())
    rendered = _patch_render_leaderboard_capture(monkeypatch)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        [
            "resume-batch",
            "BATCH123",
            "--base-url",
            "http://test:8000",
            "--db-path",
            str(tmp_path / "exp.db"),
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
        ],
    )

    assert result.exit_code == 0
    assert len(rendered["calls"]) == 1


def test_log_level_debug_is_accepted() -> None:
    result = runner.invoke(app, ["--log-level", "DEBUG", "--help"])
    assert result.exit_code == 0
    assert "--log-level" in result.stdout


def test_invalid_log_level_is_rejected() -> None:
    result = runner.invoke(app, ["--log-level", "INVALID", "run-batch", "--help"])
    assert result.exit_code != 0
    assert "Invalid value for '--log-level'" in result.output


def test_list_runs_empty_db(tmp_path) -> None:
    db_path = tmp_path / "experiments.db"
    MetadataStore(db_path).close()

    result = runner.invoke(
        app,
        [
            "list-runs",
            "--db-path",
            str(db_path),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_list_runs_with_data(populated_db: str) -> None:
    result = runner.invoke(
        app,
        [
            "list-runs",
            "--db-path",
            populated_db,
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 2
    assert payload[0]["batch_run_id"] == "bbbbbbbb-2222-2222-2222-222222222222"
    assert payload[1]["batch_run_id"] == "aaaaaaaa-1111-1111-1111-111111111111"


def test_list_runs_status_filter(populated_db: str) -> None:
    result = runner.invoke(
        app,
        [
            "list-runs",
            "--db-path",
            populated_db,
            "--status",
            "completed",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["status"] == "completed"


def test_list_runs_pagination(populated_db: str) -> None:
    result = runner.invoke(
        app,
        [
            "list-runs",
            "--db-path",
            populated_db,
            "--limit",
            "1",
            "--offset",
            "0",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1


def test_list_runs_table_format(populated_db: str) -> None:
    result = runner.invoke(
        app,
        [
            "list-runs",
            "--db-path",
            populated_db,
            "--format",
            "table",
        ],
    )

    assert result.exit_code == 0


def test_list_runs_csv_format(populated_db: str) -> None:
    result = runner.invoke(
        app,
        [
            "list-runs",
            "--db-path",
            populated_db,
            "--format",
            "csv",
        ],
    )

    assert result.exit_code == 0
    assert "batch_run_id" in result.stdout


def test_compare_runs_json_output(compare_db: tuple[str, str, str]) -> None:
    db_path, run_a, run_b = compare_db
    result = runner.invoke(
        app,
        ["compare-runs", run_a, run_b, "--db-path", db_path, "--format", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["matched"]) == 2
    assert payload["summary"]["matched_count"] == 2
    assert payload["summary"]["only_a_count"] == 1
    assert payload["summary"]["only_b_count"] == 1


def test_compare_runs_table_output(compare_db: tuple[str, str, str]) -> None:
    db_path, run_a, run_b = compare_db
    result = runner.invoke(
        app,
        ["compare-runs", run_a, run_b, "--db-path", db_path, "--format", "table"],
    )
    assert result.exit_code == 0


def test_compare_runs_resolves_latest(compare_db: tuple[str, str, str]) -> None:
    db_path, _, _ = compare_db
    result = runner.invoke(
        app,
        ["compare-runs", "latest", "latest~1", "--db-path", db_path, "--format", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "matched" in payload


def test_compare_runs_invalid_run_id(compare_db: tuple[str, str, str]) -> None:
    db_path, _, run_b = compare_db
    result = runner.invoke(
        app,
        ["compare-runs", "missing-run", run_b, "--db-path", db_path, "--format", "json"],
    )
    assert result.exit_code == 1


def test_compare_runs_all_status_flag(compare_db_mixed_status: tuple[str, str, str]) -> None:
    db_path, run_a, run_b = compare_db_mixed_status
    result = runner.invoke(
        app,
        [
            "compare-runs",
            run_a,
            run_b,
            "--db-path",
            db_path,
            "--all-status",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["matched"]) == 1
    assert payload["matched"][0]["run_a_status"] == "failed"


def test_show_run_json_output(compare_db: tuple[str, str, str]) -> None:
    db_path, run_a, _ = compare_db
    result = runner.invoke(
        app,
        ["show-run", run_a, "--db-path", db_path, "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["batch_run"]["batch_run_id"] == run_a
    assert isinstance(payload["scenarios"], list)


def test_show_run_table_output(compare_db: tuple[str, str, str]) -> None:
    db_path, run_a, _ = compare_db
    result = runner.invoke(
        app,
        ["show-run", run_a, "--db-path", db_path, "--format", "table"],
    )
    assert result.exit_code == 0


def test_show_run_latest_selector(compare_db: tuple[str, str, str]) -> None:
    db_path, _, run_b = compare_db
    result = runner.invoke(
        app,
        ["show-run", "latest", "--db-path", db_path, "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["batch_run"]["batch_run_id"] == run_b


def test_show_run_not_found(compare_db: tuple[str, str, str]) -> None:
    db_path, _, _ = compare_db
    result = runner.invoke(
        app,
        ["show-run", "missing-run", "--db-path", db_path, "--format", "json"],
    )
    assert result.exit_code == 1
