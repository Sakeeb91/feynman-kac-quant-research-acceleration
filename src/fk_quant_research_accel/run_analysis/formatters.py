"""Output formatters for run analysis commands."""

from __future__ import annotations

import csv
import json
import math
import sys
from typing import Literal
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

OutputFormat = Literal["table", "json", "csv"]

_HEALTH_STYLES: dict[str, str] = {
    "healthy": "green",
    "oscillating": "yellow",
    "stagnating": "yellow",
    "exploding": "red",
}


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


def _format_health(health: str | None) -> Text:
    label = str(health or "--")
    return Text(label, style=_HEALTH_STYLES.get(label, "white"))


def _parse_json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _scenario_compact(scenario: dict[str, Any]) -> str:
    return (
        f"d={scenario.get('dim', '--')}/"
        f"v={scenario.get('volatility', '--')}/"
        f"c={scenario.get('correlation', '--')}/"
        f"t={scenario.get('option_type', '--')}"
    )


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


def emit_comparison_table(
    comparison: dict[str, Any],
    *,
    verbose: bool = False,
    console: Console | None = None,
) -> None:
    active_console = console or Console(stderr=True)
    summary = comparison.get("summary", {})
    active_console.print(
        Panel(
            (
                f"Matched: {summary.get('matched_count', 0)} | "
                f"Only in A: {summary.get('only_a_count', 0)} | "
                f"Only in B: {summary.get('only_b_count', 0)} | "
                f"A wins: {summary.get('a_wins', 0)} | "
                f"B wins: {summary.get('b_wins', 0)}"
            ),
            title="Comparison Summary",
        )
    )

    table = Table(title="Run Comparison")
    table.add_column("Scenario")
    table.add_column("Score A", justify="right")
    table.add_column("Score B", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Delta %", justify="right")
    table.add_column("Status", justify="center")
    if verbose:
        table.add_column("Train Δ", justify="right")
        table.add_column("Grad Δ", justify="right")
        table.add_column("Prog Δ", justify="right")

    for row in comparison.get("matched", []):
        score_delta = row.get("delta_abs_score")
        delta_style = "white"
        if isinstance(score_delta, (int, float)):
            if score_delta < 0:
                delta_style = "green"
            elif score_delta > 0:
                delta_style = "red"

        status_prefix = "[!]" if row.get("status_mismatch") else ""
        cells = [
            _scenario_compact(row.get("scenario", {})),
            _format_score(row.get("run_a_score")),
            _format_score(row.get("run_b_score")),
            f"[{delta_style}]{_format_score(score_delta)}[/{delta_style}]",
            _format_score(row.get("delta_pct_score")),
            f"{status_prefix}{row.get('run_a_status', '--')}|{row.get('run_b_status', '--')}",
        ]
        if verbose:
            cells.extend(
                [
                    _format_score(row.get("delta_abs_train_loss")),
                    _format_score(row.get("delta_abs_grad_norm")),
                    _format_score(row.get("delta_abs_progress")),
                ]
            )
        table.add_row(*cells)
    active_console.print(table)


def emit_comparison_json(comparison: dict[str, Any]) -> None:
    print(json.dumps(comparison, indent=2, default=str))


def emit_comparison_csv(comparison: dict[str, Any]) -> None:
    rows = list(comparison.get("matched", []))
    if not rows:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)


def emit_show_run(
    batch_run: dict[str, Any],
    scenarios: list[dict[str, Any]],
    *,
    verbose: bool = False,
    console: Console | None = None,
) -> None:
    active_console = console or Console(stderr=True)
    active_console.print(
        Panel(
            (
                f"Run ID: {batch_run.get('batch_run_id', '--')}\n"
                f"Created: {batch_run.get('created_at', '--')}\n"
                f"Status: {batch_run.get('status', '--')}\n"
                f"Git SHA: {batch_run.get('git_sha', '--')}\n"
                f"Scenario Count: {batch_run.get('scenario_count', '--')}"
            ),
            title="Run Details",
            border_style="blue",
        )
    )

    table = Table(title="Scenario Details")
    table.add_column("Scenario ID", no_wrap=True)
    table.add_column("Dim", justify="right")
    table.add_column("Vol", justify="right")
    table.add_column("Corr", justify="right")
    table.add_column("Type")
    table.add_column("Status", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Health", justify="center")
    table.add_column("Train Loss", justify="right")
    table.add_column("Grad Norm", justify="right")
    table.add_column("Progress", justify="right")
    if verbose:
        table.add_column("Error")
        table.add_column("Checkpoint")

    for scenario_row in scenarios:
        scenario_payload = _parse_json_object(scenario_row.get("scenario_json"))
        result_payload = _parse_json_object(scenario_row.get("result_json"))
        cells: list[Any] = [
            str(scenario_row.get("scenario_run_id", "--"))[:12],
            str(scenario_payload.get("dim", "--")),
            _format_score(scenario_payload.get("volatility")),
            str(scenario_payload.get("correlation", "--")),
            str(scenario_payload.get("option_type", "--")),
            str(scenario_row.get("status", "--")),
            _format_score(result_payload.get("score")),
            _format_health(result_payload.get("convergence_health")),
            _format_score(result_payload.get("train_loss")),
            _format_score(result_payload.get("grad_norm")),
            _format_score(result_payload.get("progress")),
        ]
        if verbose:
            cells.append(str(scenario_row.get("error_message", "--")))
            cells.append(str(scenario_row.get("checkpoint_path", "--")))
        table.add_row(*cells)
    active_console.print(table)


def emit_show_run_json(batch_run: dict[str, Any], scenarios: list[dict[str, Any]]) -> None:
    print(
        json.dumps(
            {
                "batch_run": batch_run,
                "scenarios": scenarios,
            },
            indent=2,
            default=str,
        )
    )


def emit_show_run_csv(scenarios: list[dict[str, Any]]) -> None:
    flattened: list[dict[str, Any]] = []
    for scenario_row in scenarios:
        scenario_payload = _parse_json_object(scenario_row.get("scenario_json"))
        result_payload = _parse_json_object(scenario_row.get("result_json"))
        flattened.append(
            {
                "scenario_run_id": scenario_row.get("scenario_run_id"),
                "status": scenario_row.get("status"),
                "dim": scenario_payload.get("dim"),
                "volatility": scenario_payload.get("volatility"),
                "correlation": scenario_payload.get("correlation"),
                "option_type": scenario_payload.get("option_type"),
                "score": result_payload.get("score"),
                "convergence_health": result_payload.get("convergence_health"),
                "train_loss": result_payload.get("train_loss"),
                "grad_norm": result_payload.get("grad_norm"),
                "progress": result_payload.get("progress"),
                "error_message": scenario_row.get("error_message"),
                "checkpoint_path": scenario_row.get("checkpoint_path"),
            }
        )
    if not flattened:
        return
    writer = csv.DictWriter(sys.stdout, fieldnames=list(flattened[0].keys()))
    writer.writeheader()
    writer.writerows(flattened)
