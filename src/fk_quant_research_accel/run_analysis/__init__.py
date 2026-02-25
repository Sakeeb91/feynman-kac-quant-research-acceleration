"""Run analysis helpers for listing and resolving experiment runs."""

from .resolver import resolve_run_id
from .queries import list_runs_with_metrics
from .formatters import (
    emit_comparison_csv,
    emit_comparison_json,
    emit_comparison_table,
    emit_show_run,
    emit_show_run_csv,
    emit_show_run_json,
    get_effective_format,
)
from .comparison import align_scenarios, compute_comparison, delta_abs, delta_pct

__all__ = [
    "resolve_run_id",
    "list_runs_with_metrics",
    "get_effective_format",
    "align_scenarios",
    "compute_comparison",
    "delta_abs",
    "delta_pct",
    "emit_comparison_table",
    "emit_comparison_json",
    "emit_comparison_csv",
    "emit_show_run",
    "emit_show_run_json",
    "emit_show_run_csv",
]
