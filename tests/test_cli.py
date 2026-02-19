from __future__ import annotations

from typer.testing import CliRunner

from fk_quant_research_accel.cli import app


runner = CliRunner()


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
    ]:
        assert flag in result.stdout
