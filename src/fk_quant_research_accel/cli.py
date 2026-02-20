"""CLI for running quant research batches on top of FK PINN backend."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import structlog
import typer

from .client import FKPinnClient
from .logging import configure_logging
from .models import LogLevel, content_hash, load_manifest
from .orchestrator import (
    BatchConfig,
    generate_black_scholes_scenarios,
    generate_scenarios_from_manifest,
    run_batch,
)
from .reporting import write_csv
from .validation import validate_manifest

app = typer.Typer(name="fk-research", help="FK Quant Research Acceleration Platform")


def _parse_int_list(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_float_list(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _log_top(rows: Iterable[dict], n: int = 10) -> None:
    log = structlog.get_logger()
    for idx, row in enumerate(rows):
        if idx >= n:
            break
        log.info(
            "top_scenario",
            rank=idx + 1,
            score=row["score"],
            dim=row["dim"],
            volatility=row["volatility"],
            correlation=row["correlation"],
            option_type=row["option_type"],
            status=row["status"],
            train_loss=row["train_loss"],
        )


@app.callback()
def main_callback(
    log_level: LogLevel = typer.Option(LogLevel.INFO, "--log-level", case_sensitive=False),
) -> None:
    configure_logging(log_level.value)


@app.command("run-batch")
def run_batch_command(
    base_url: str = typer.Option(..., "--base-url"),
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
    output: str = typer.Option("artifacts/batch_results.csv", "--output"),
) -> None:
    log = structlog.get_logger()
    client = FKPinnClient(base_url=base_url)
    scenarios = generate_black_scholes_scenarios(
        dimensions=_parse_int_list(dimensions),
        volatilities=_parse_float_list(volatilities),
        correlations=_parse_float_list(correlations),
        option_types=[item.strip() for item in option_types.split(",") if item.strip()],
    )
    config = BatchConfig(
        n_steps=n_steps,
        batch_size=batch_size,
        n_mc_paths=n_mc_paths,
        learning_rate=learning_rate,
    )
    rows = run_batch(
        client=client,
        scenarios=scenarios,
        batch_config=config,
        poll_seconds=poll_seconds,
        max_wait_seconds=max_wait_seconds,
    )
    output_path = write_csv(rows, output)
    _log_top(rows)
    log.info("batch_complete", rows=len(rows), output=str(output_path))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
