"""Rich leaderboard renderer for batch results."""

from __future__ import annotations

import math
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models.enums import ConvergenceHealth

_HEALTH_STYLES: dict[str, str] = {
    ConvergenceHealth.HEALTHY.value: "green",
    ConvergenceHealth.OSCILLATING.value: "yellow",
    ConvergenceHealth.STAGNATING.value: "yellow",
    ConvergenceHealth.EXPLODING.value: "red",
}


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


def _format_corr(value: Any) -> str:
    if value is None:
        return "--"
    if isinstance(value, list):
        if value and isinstance(value[0], list):
            rows = len(value)
            cols = len(value[0]) if value[0] else 0
            return f"[{rows}x{cols}]"
        return ",".join(str(item) for item in value)
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def render_leaderboard(
    records: list[dict[str, Any]],
    n: int = 10,
    title: str = "Leaderboard",
    console: Console | None = None,
) -> None:
    if console is None:
        console = Console(stderr=True)

    table = Table(
        title=title,
        caption=f"Top {min(n, len(records))} of {len(records)} scenarios",
    )
    table.add_column("Rank", justify="right", style="bold", width=6)
    table.add_column("Score", justify="right", style="cyan", width=12)
    table.add_column("Health", justify="center", width=12)
    table.add_column("Dim", justify="right", width=5)
    table.add_column("Vol", justify="right", width=8)
    table.add_column("Corr", justify="right", width=8)
    table.add_column("Type", width=10)
    table.add_column("Loss", justify="right", width=12)
    table.add_column("Status", justify="center", width=10)

    for rank, row in enumerate(records[:n], start=1):
        table.add_row(
            str(rank),
            _format_score(row.get("score")),
            _format_health(row.get("convergence_health")),
            str(row.get("dim", "--")),
            _format_score(row.get("volatility")),
            _format_corr(row.get("correlation")),
            str(row.get("option_type", "--")),
            _format_score(row.get("train_loss")),
            str(row.get("status", "--")),
        )

    console.print(table)
