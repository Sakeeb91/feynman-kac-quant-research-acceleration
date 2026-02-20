from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

import fk_quant_research_accel.cli as cli_module
from fk_quant_research_accel.cli import app


runner = CliRunner()


class FakeClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url


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
        "--output",
        "--manifest",
    ]:
        assert flag in result.stdout


def test_cli_manifest_option_exists_in_help() -> None:
    result = runner.invoke(app, ["run-batch", "--help"])

    assert result.exit_code == 0
    assert "--manifest" in result.stdout


def test_log_level_debug_is_accepted() -> None:
    result = runner.invoke(app, ["--log-level", "DEBUG", "--help"])
    assert result.exit_code == 0
    assert "--log-level" in result.stdout


def test_invalid_log_level_is_rejected() -> None:
    result = runner.invoke(app, ["--log-level", "INVALID", "run-batch", "--help"])
    assert result.exit_code != 0
    assert "Invalid value for '--log-level'" in result.output
