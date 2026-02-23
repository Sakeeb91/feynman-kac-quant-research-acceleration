from __future__ import annotations

import json
from datetime import UTC, datetime
from io import StringIO

import pytest
from rich.console import Console

from fk_quant_research_accel.store.metadata import MetadataStore
from fk_quant_research_accel.run_analysis.formatters import get_effective_format
from fk_quant_research_accel.run_analysis.resolver import resolve_run_id
from fk_quant_research_accel.run_analysis.queries import list_runs_with_metrics


def _insert_batch(
    store: MetadataStore,
    tmp_path,
    *,
    batch_run_id: str,
    created_at: str,
) -> None:
    store.create_batch_run(
        batch_run_id=batch_run_id,
        created_at=created_at,
        config_json=json.dumps({"n_steps": 40}),
        manifest_schema_version=1,
        git_sha="abc123",
        git_dirty=False,
        python_version="3.12.0",
        os_info="test-os",
        seed=7,
        scenario_count=1,
        artifact_path=str(tmp_path / "artifacts" / batch_run_id),
    )


def _insert_scenario(
    store: MetadataStore,
    *,
    batch_run_id: str,
    score: float | None,
    status: str = "completed",
) -> None:
    scenario_id = f"scenario-{datetime.now(UTC).timestamp()}-{score}"
    store.create_scenario_run(
        scenario_run_id=scenario_id,
        batch_run_id=batch_run_id,
        scenario_json=json.dumps({"dim": 5}),
        created_at=datetime.now(UTC).isoformat(),
    )
    store.persist_scenario_result(
        scenario_run_id=scenario_id,
        status=status,
        result_json=json.dumps({"status": status, "score": score}),
        score=score,
        completed_at=datetime.now(UTC).isoformat(),
    )


def test_resolve_run_id_full_uuid(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    batch_run_id = "11111111-1111-1111-1111-111111111111"
    _insert_batch(
        store,
        tmp_path,
        batch_run_id=batch_run_id,
        created_at=datetime.now(UTC).isoformat(),
    )

    resolved = resolve_run_id(batch_run_id, store)
    store.close()
    assert resolved == batch_run_id


def test_resolve_run_id_prefix(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    batch_run_id = "22222222-2222-2222-2222-222222222222"
    _insert_batch(
        store,
        tmp_path,
        batch_run_id=batch_run_id,
        created_at=datetime.now(UTC).isoformat(),
    )

    resolved = resolve_run_id(batch_run_id[:10], store)
    store.close()
    assert resolved == batch_run_id


def test_resolve_run_id_prefix_too_short(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    with pytest.raises(ValueError, match="at least 8 characters"):
        resolve_run_id("abc", store)
    store.close()


def test_resolve_run_id_prefix_ambiguous(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    first = "aaaaaaaa-1111-1111-1111-111111111111"
    second = "aaaaaaaa-2222-2222-2222-222222222222"
    _insert_batch(store, tmp_path, batch_run_id=first, created_at="2025-01-01T00:00:00+00:00")
    _insert_batch(store, tmp_path, batch_run_id=second, created_at="2025-01-02T00:00:00+00:00")

    with pytest.raises(ValueError, match="Ambiguous"):
        resolve_run_id("aaaaaaaa", store)
    store.close()


def test_resolve_run_id_prefix_not_found(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    with pytest.raises(ValueError, match="No run found"):
        resolve_run_id("zzzzzzzz", store)
    store.close()


def test_resolve_run_id_latest(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    first = "bbbbbbbb-1111-1111-1111-111111111111"
    second = "bbbbbbbb-2222-2222-2222-222222222222"
    third = "bbbbbbbb-3333-3333-3333-333333333333"
    _insert_batch(store, tmp_path, batch_run_id=first, created_at="2025-01-01T00:00:00+00:00")
    _insert_batch(store, tmp_path, batch_run_id=second, created_at="2025-01-02T00:00:00+00:00")
    _insert_batch(store, tmp_path, batch_run_id=third, created_at="2025-01-03T00:00:00+00:00")

    resolved = resolve_run_id("latest", store)
    store.close()
    assert resolved == third


def test_resolve_run_id_latest_tilde_n(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    first = "cccccccc-1111-1111-1111-111111111111"
    second = "cccccccc-2222-2222-2222-222222222222"
    third = "cccccccc-3333-3333-3333-333333333333"
    _insert_batch(store, tmp_path, batch_run_id=first, created_at="2025-01-01T00:00:00+00:00")
    _insert_batch(store, tmp_path, batch_run_id=second, created_at="2025-01-02T00:00:00+00:00")
    _insert_batch(store, tmp_path, batch_run_id=third, created_at="2025-01-03T00:00:00+00:00")

    resolved_second_newest = resolve_run_id("latest~1", store)
    resolved_oldest = resolve_run_id("latest~2", store)
    store.close()

    assert resolved_second_newest == second
    assert resolved_oldest == first


def test_resolve_run_id_latest_out_of_range(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    _insert_batch(
        store,
        tmp_path,
        batch_run_id="dddddddd-1111-1111-1111-111111111111",
        created_at="2025-01-01T00:00:00+00:00",
    )

    with pytest.raises(ValueError, match="No run found"):
        resolve_run_id("latest~5", store)
    store.close()


def test_list_runs_with_metrics_adds_median(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    batch_run_id = "eeeeeeee-1111-1111-1111-111111111111"
    _insert_batch(
        store,
        tmp_path,
        batch_run_id=batch_run_id,
        created_at="2025-01-01T00:00:00+00:00",
    )
    _insert_scenario(store, batch_run_id=batch_run_id, score=0.1)
    _insert_scenario(store, batch_run_id=batch_run_id, score=0.3)
    _insert_scenario(store, batch_run_id=batch_run_id, score=0.5)

    rows = list_runs_with_metrics(store)
    store.close()

    assert len(rows) == 1
    assert rows[0]["best_score"] == 0.1
    assert rows[0]["median_score"] == 0.3


def test_list_runs_with_metrics_no_completed_scenarios(tmp_path) -> None:
    store = MetadataStore(tmp_path / "experiments.db")
    batch_run_id = "ffffffff-1111-1111-1111-111111111111"
    _insert_batch(
        store,
        tmp_path,
        batch_run_id=batch_run_id,
        created_at="2025-01-01T00:00:00+00:00",
    )
    _insert_scenario(store, batch_run_id=batch_run_id, score=None, status="failed")

    rows = list_runs_with_metrics(store)
    store.close()

    assert len(rows) == 1
    assert rows[0]["best_score"] is None
    assert rows[0]["median_score"] is None


def test_get_effective_format_explicit_override() -> None:
    assert get_effective_format("json") == "json"


def test_get_effective_format_none_tty() -> None:
    console = Console(file=StringIO(), force_terminal=True)
    assert get_effective_format(None, console=console) == "table"
