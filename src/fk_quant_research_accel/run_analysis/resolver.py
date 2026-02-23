"""Run selector resolution helpers."""

from __future__ import annotations

import re

from fk_quant_research_accel.store.metadata import MetadataStore

_LATEST_SELECTOR = re.compile(r"^latest(?:~(\d+))?$")


def resolve_run_id(selector: str, store: MetadataStore) -> str:
    latest_match = _LATEST_SELECTOR.match(selector)
    if latest_match:
        offset = int(latest_match.group(1) or "0")
        latest = store.list_batch_runs(limit=1, offset=offset)
        if not latest:
            raise ValueError(f"No run found for selector: {selector}")
        return str(latest[0]["batch_run_id"])

    if len(selector) < 8:
        raise ValueError("Run selector prefix must be at least 8 characters")
    matches = store.find_batch_runs_by_prefix(selector)
    if len(matches) == 1:
        return str(matches[0]["batch_run_id"])
    if len(matches) > 1:
        raise ValueError(f"Ambiguous run selector: {selector}")
    raise ValueError(f"No run found for selector: {selector}")
