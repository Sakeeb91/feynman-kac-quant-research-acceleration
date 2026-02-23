from __future__ import annotations

import json
from datetime import UTC, datetime

from fk_quant_research_accel.store.metadata import MetadataStore
from fk_quant_research_accel.run_analysis.resolver import resolve_run_id


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
