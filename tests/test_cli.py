from __future__ import annotations

from typing import Any
from pathlib import Path

import yaml
from typer.testing import CliRunner

import fk_quant_research_accel.cli as cli_module
from fk_quant_research_accel.cli import app
from fk_quant_research_accel.validation import PreflightError


runner = CliRunner()


def _ok_rows() -> list[dict[str, Any]]:
    return [
        {
            "score": 0.1,
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


def _write_manifest(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return path


def test_help_includes_program_name_and_log_level() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "fk-research" in result.stdout
    assert "--log-level" in result.stdout


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


def test_cli_manifest_loads_and_validates(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_run_batch(**kwargs):
        captured.update(kwargs)
        return [
            {
                "score": 0.1,
                "dim": 5,
                "volatility": 0.2,
                "correlation": 0.0,
                "option_type": "call",
                "status": "completed",
                "train_loss": 0.1,
            }
        ]

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
        },
    )

    monkeypatch.setattr(cli_module, "FKPinnClient", FakeClient)
    monkeypatch.setattr(cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(cli_module, "_log_top", lambda rows, n=10: None)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(
        app,
        ["run-batch", "--manifest", str(manifest_path), "--output", str(tmp_path / "out.csv")],
    )

    assert result.exit_code == 0
    assert isinstance(captured["client"], FakeClient)
    assert captured["client"].base_url == "http://manifest-backend:9000"
    assert captured["experiment_manifest_hash"] is not None
    assert captured["seed"] == 123
    assert str(captured["artifacts_dir"]).endswith("artifacts")


def test_cli_manifest_preflight_fails_exits_1(monkeypatch, tmp_path) -> None:
    called = {"run_batch": False}

    def fake_run_batch(**kwargs):
        called["run_batch"] = True
        del kwargs
        return []

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

    monkeypatch.setattr(cli_module, "FKPinnClient", FakeClient)
    monkeypatch.setattr(cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(cli_module, "_log_top", lambda rows, n=10: None)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(app, ["run-batch", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert called["run_batch"] is False


def test_cli_backward_compat_flags(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_run_batch(**kwargs):
        captured.update(kwargs)
        return [
            {
                "score": 0.1,
                "dim": 5,
                "volatility": 0.2,
                "correlation": 0.0,
                "option_type": "call",
                "status": "completed",
                "train_loss": 0.1,
            }
        ]

    monkeypatch.setattr(cli_module, "FKPinnClient", FakeClient)
    monkeypatch.setattr(cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(cli_module, "_log_top", lambda rows, n=10: None)
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
    assert isinstance(captured["client"], FakeClient)
    assert captured["client"].base_url == "http://legacy-backend:8000"


def test_cli_base_url_required_without_manifest() -> None:
    result = runner.invoke(app, ["run-batch"])

    assert result.exit_code != 0
    assert "--base-url is required when --manifest is not provided" in result.output


def test_cli_manifest_overrides_legacy_flags(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_run_batch(**kwargs):
        captured.update(kwargs)
        return [
            {
                "score": 0.1,
                "dim": 5,
                "volatility": 0.2,
                "correlation": 0.0,
                "option_type": "call",
                "status": "completed",
                "train_loss": 0.1,
            }
        ]

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

    monkeypatch.setattr(cli_module, "FKPinnClient", FakeClient)
    monkeypatch.setattr(cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(cli_module, "_log_top", lambda rows, n=10: None)
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
    assert isinstance(captured["client"], FakeClient)
    assert captured["client"].base_url == "http://manifest-backend:9000"
    assert len(captured["scenarios"]) == 1


def test_cli_manifest_load_failure_exits_1(monkeypatch, tmp_path) -> None:
    called = {"run_batch": False}

    def fake_run_batch(**kwargs):
        called["run_batch"] = True
        del kwargs
        return []

    manifest_path = tmp_path / "broken.yaml"
    manifest_path.write_text("backend_url: [unclosed", encoding="utf-8")

    monkeypatch.setattr(cli_module, "FKPinnClient", FakeClient)
    monkeypatch.setattr(cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(cli_module, "_log_top", lambda rows, n=10: None)
    monkeypatch.setattr(cli_module, "write_csv", lambda rows, output: Path(output))

    result = runner.invoke(app, ["run-batch", "--manifest", str(manifest_path)])

    assert result.exit_code == 1
    assert called["run_batch"] is False


def test_cli_manifest_preflight_logs_all_errors(monkeypatch, tmp_path) -> None:
    called = {"run_batch": False}

    def fake_run_batch(**kwargs):
        called["run_batch"] = True
        del kwargs
        return []

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

    monkeypatch.setattr(cli_module, "FKPinnClient", FakeClient)
    monkeypatch.setattr(cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(cli_module, "_log_top", lambda rows, n=10: None)
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
    assert called["run_batch"] is False


def test_log_level_debug_is_accepted() -> None:
    result = runner.invoke(app, ["--log-level", "DEBUG", "--help"])
    assert result.exit_code == 0
    assert "--log-level" in result.stdout


def test_invalid_log_level_is_rejected() -> None:
    result = runner.invoke(app, ["--log-level", "INVALID", "run-batch", "--help"])
    assert result.exit_code != 0
    assert "Invalid value for '--log-level'" in result.output
