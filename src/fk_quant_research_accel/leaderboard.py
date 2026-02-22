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
    _ = (records, n, title)
    if console is None:
        console = Console(stderr=True)
    table = Table(title=title)
    console.print(table)
