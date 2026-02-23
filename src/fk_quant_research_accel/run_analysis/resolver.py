"""Run selector resolution helpers."""

from __future__ import annotations

from fk_quant_research_accel.store.metadata import MetadataStore


def resolve_run_id(selector: str, store: MetadataStore) -> str:
    if len(selector) < 8:
        raise ValueError("Run selector prefix must be at least 8 characters")
    matches = store.find_batch_runs_by_prefix(selector)
    if len(matches) == 1:
        return str(matches[0]["batch_run_id"])
    if len(matches) > 1:
        raise ValueError(f"Ambiguous run selector: {selector}")
    raise ValueError(f"No run found for selector: {selector}")
