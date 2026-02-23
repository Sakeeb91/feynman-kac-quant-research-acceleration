"""Output formatters for run analysis commands."""

from __future__ import annotations

from typing import Literal

from rich.console import Console

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
