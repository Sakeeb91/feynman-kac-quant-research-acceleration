"""CLI for running quant research batches on top of FK PINN backend."""

from __future__ import annotations

import anyio
from functools import partial
from pathlib import Path

import structlog
import typer

from .async_client import AsyncFKPinnClient
from .logging import configure_logging
from .leaderboard import render_leaderboard
from .models import ExperimentManifest, LogLevel, ScoringConfig, content_hash, load_manifest
from .async_orchestrator import resume_batch_async, run_batch_async
from .orchestrator import (
    BatchConfig,
    generate_black_scholes_scenarios,
    generate_scenarios_from_manifest,
)
from .reporting import write_csv
from .validation import validate_manifest

app = typer.Typer(name="fk-research", help="FK Quant Research Acceleration Platform")


def _parse_int_list(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_float_list(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_str_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _batch_config_from_manifest(experiment: ExperimentManifest) -> BatchConfig:
    return BatchConfig(
        n_steps=experiment.batch_config.n_steps,
        batch_size=experiment.batch_config.batch_size,
        n_mc_paths=experiment.batch_config.n_mc_paths,
        learning_rate=experiment.batch_config.learning_rate,
    )


def _batch_config_from_flags(
    n_steps: int,
    batch_size: int,
    n_mc_paths: int,
    learning_rate: float,
) -> BatchConfig:
    return BatchConfig(
        n_steps=n_steps,
        batch_size=batch_size,
        n_mc_paths=n_mc_paths,
        learning_rate=learning_rate,
    )


@app.callback()
def main_callback(
    log_level: LogLevel = typer.Option(LogLevel.INFO, "--log-level", case_sensitive=False),
) -> None:
    configure_logging(log_level.value)


@app.command("run-batch")
def run_batch_command(
    base_url: str | None = typer.Option(None, "--base-url"),
    manifest: Path | None = typer.Option(
        None,
        "--manifest",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to experiment YAML manifest. Overrides all other config flags.",
    ),
    dimensions: str = typer.Option("5,10", "--dimensions"),
    volatilities: str = typer.Option("0.15,0.2", "--volatilities"),
    correlations: str = typer.Option("0.0,0.3", "--correlations"),
    option_types: str = typer.Option("call", "--option-types"),
    n_steps: int = typer.Option(40, "--n-steps"),
    batch_size: int = typer.Option(64, "--batch-size"),
    n_mc_paths: int = typer.Option(256, "--n-mc-paths"),
    learning_rate: float = typer.Option(1e-3, "--learning-rate"),
    poll_seconds: float = typer.Option(1.5, "--poll-seconds"),
    max_wait_seconds: float = typer.Option(1800.0, "--max-wait-seconds"),
    concurrency: int = typer.Option(
        20,
        "--concurrency",
        min=1,
        max=100,
        help="Max concurrent scenario executions",
    ),
    max_retries: int = typer.Option(
        3,
        "--max-retries",
        min=0,
        max=10,
        help="Max retry attempts per transient HTTP error",
    ),
    output: str = typer.Option("artifacts/batch_results.csv", "--output"),
) -> None:
    log = structlog.get_logger()
    if manifest is None and not base_url:
        raise typer.BadParameter("--base-url is required when --manifest is not provided")

    effective_poll_seconds = poll_seconds
    effective_max_wait_seconds = max_wait_seconds
    artifacts_dir: str | Path = "artifacts"
    db_path: str | Path | None = None
    seed: int | None = None
    experiment_manifest_hash: str | None = None
    effective_scoring_config = ScoringConfig()
    backend_base_url: str | None = base_url

    if manifest is not None:
        try:
            experiment = load_manifest(manifest)
        except ValueError as exc:
            log.error("manifest_load_failed", path=str(manifest), error=str(exc))
            raise typer.Exit(code=1) from exc

        experiment_manifest_hash = content_hash(experiment)
        log.info(
            "manifest_loaded",
            path=str(manifest),
            hash=experiment_manifest_hash,
        )
        preflight_errors = validate_manifest(experiment)
        if preflight_errors:
            for error in preflight_errors:
                log.error(
                    "preflight_validation_failed",
                    field=error.field,
                    value=error.value,
                    message=error.message,
                )
            raise typer.Exit(code=1)

        scenarios = generate_scenarios_from_manifest(experiment)
        log.info(
            "preflight_passed",
            scenario_count=len(scenarios),
            hash=experiment_manifest_hash,
        )
        config = _batch_config_from_manifest(experiment)
        backend_base_url = experiment.backend_url
        effective_poll_seconds = experiment.batch_config.poll_seconds
        effective_max_wait_seconds = experiment.batch_config.max_wait_seconds
        artifacts_dir = experiment.output.artifacts_dir
        db_path = experiment.output.db_path
        seed = experiment.seed
        effective_scoring_config = experiment.scoring
    else:
        assert base_url is not None
        backend_base_url = base_url
        scenarios = generate_black_scholes_scenarios(
            dimensions=_parse_int_list(dimensions),
            volatilities=_parse_float_list(volatilities),
            correlations=_parse_float_list(correlations),
            option_types=_parse_str_list(option_types),
        )
        config = _batch_config_from_flags(
            n_steps=n_steps,
            batch_size=batch_size,
            n_mc_paths=n_mc_paths,
            learning_rate=learning_rate,
        )

    assert backend_base_url is not None
    async_client = AsyncFKPinnClient(
        base_url=backend_base_url,
        concurrency_limit=concurrency,
    )

    rows = anyio.run(
        partial(
            run_batch_async,
            client=async_client,
            scenarios=scenarios,
            batch_config=config,
            poll_seconds=effective_poll_seconds,
            max_wait_seconds=effective_max_wait_seconds,
            concurrency_limit=concurrency,
            max_retries=max_retries,
            artifacts_dir=artifacts_dir,
            db_path=db_path,
            seed=seed,
            experiment_manifest_hash=experiment_manifest_hash,
            scoring_config=effective_scoring_config,
        )
    )
    output_path = write_csv(rows, output)
    _log_top(rows)
    log.info("batch_complete", rows=len(rows), output=str(output_path))


@app.command("resume-batch")
def resume_batch_command(
    batch_run_id: str = typer.Argument(
        ...,
        help="Batch run ID to resume (from previous run-batch output)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-run ALL scenarios, including completed ones",
    ),
    concurrency: int = typer.Option(
        20,
        "--concurrency",
        min=1,
        max=100,
        help="Max concurrent scenario executions",
    ),
    max_retries: int = typer.Option(
        3,
        "--max-retries",
        min=0,
        max=10,
        help="Max retry attempts per transient HTTP error",
    ),
    base_url: str = typer.Option(
        ...,
        "--base-url",
        help="FK PINN backend URL",
    ),
    poll_seconds: float = typer.Option(2.0, "--poll-seconds"),
    max_wait_seconds: float = typer.Option(1800.0, "--max-wait-seconds"),
    db_path: str = typer.Option("artifacts/experiments.db", "--db-path"),
    artifacts_dir: str = typer.Option("artifacts", "--artifacts-dir"),
    output: str = typer.Option("artifacts/resume_results.csv", "--output"),
) -> None:
    log = structlog.get_logger()
    log.info("resume_batch_started", batch_run_id=batch_run_id, force=force)

    async_client = AsyncFKPinnClient(base_url=base_url, concurrency_limit=concurrency)
    try:
        rows = anyio.run(
            partial(
                resume_batch_async,
                client=async_client,
                batch_run_id=batch_run_id,
                force=force,
                concurrency_limit=concurrency,
                max_retries=max_retries,
                poll_seconds=poll_seconds,
                max_wait_seconds=max_wait_seconds,
                db_path=db_path,
                artifacts_dir=artifacts_dir,
            )
        )
    except ValueError as exc:
        log.error("resume_batch_failed", batch_run_id=batch_run_id, error=str(exc))
        raise typer.Exit(code=1) from exc

    output_path = write_csv(rows, output)
    _log_top(rows)
    log.info("resume_batch_complete", rows=len(rows), output=str(output_path))

def main() -> None:
    app()


if __name__ == "__main__":
    main()
