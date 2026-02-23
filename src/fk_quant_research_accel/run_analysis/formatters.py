"""Output formatters for run analysis commands."""

from __future__ import annotations

import csv
import json
import math
import sys
from typing import Literal
from typing import Any

from rich.console import Console
from rich.table import Table

OutputFormat = Literal["table", "json", "csv"]


def get_effective_format(
    explicit: OutputFormat | None,
    *,
    console: Console | None = None,
) -> OutputFormat:
    if explicit is not None:
        return explicit
    active_console = console or Console()
    if active_console.is_terminal:
        return "table"
    return "json"


def _format_score(value: Any) -> str:
    if value is None:
        return "--"
    try:
        score = float(value)
    except (TypeError, ValueError):
        return "--"
    if math.isinf(score):
        return "inf"
    if math.isnan(score):
        return "nan"
    return f"{score:.6f}"


def emit_runs_table(
    runs: list[dict[str, Any]],
    *,
    verbose: bool = False,
    console: Console | None = None,
) -> None:
    active_console = console or Console(stderr=True)
    table = Table(title="Runs")
    table.add_column("Run ID", style="cyan", no_wrap=True)
    table.add_column("Created", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Scenarios", justify="right")
    table.add_column("Done/Fail", justify="right")
    table.add_column("Best Score", justify="right", style="green")
    table.add_column("Median Score", justify="right", style="green")
    if verbose:
        table.add_column("Git SHA")
        table.add_column("Manifest Hash")

    for run in runs:
        row = [
            str(run.get("batch_run_id", "--"))[:12],
            str(run.get("created_at", "--")),
            str(run.get("status", "--")),
            str(run.get("scenario_count", "--")),
            f"{run.get('completed_count', 0)}/{run.get('failed_count', 0)}",
            _format_score(run.get("best_score")),
            _format_score(run.get("median_score")),
        ]
        if verbose:
            row.append(str(run.get("git_sha", "--")))
            row.append(str(run.get("manifest_hash", "--")))
        table.add_row(*row)
    active_console.print(table)


def emit_json(records: list[dict[str, Any]]) -> None:
    print(json.dumps(records, indent=2, default=str))


def emit_csv(records: list[dict[str, Any]]) -> None:
    if not records:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(records[0].keys()))
    writer.writeheader()
    writer.writerows(records)
