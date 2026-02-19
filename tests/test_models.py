from __future__ import annotations

import uuid

from fk_quant_research_accel.models import (
    ScenarioStatus,
    generate_batch_run_id,
    generate_scenario_run_id,
)


def test_generate_batch_run_id_is_uuid_and_unique() -> None:
    first = generate_batch_run_id()
    second = generate_batch_run_id()

    assert isinstance(first, str)
    assert isinstance(second, str)
    uuid.UUID(first)
    uuid.UUID(second)
    assert first != second


def test_generate_scenario_run_id_is_uuid_and_unique() -> None:
    first = generate_scenario_run_id()
    second = generate_scenario_run_id()

    assert isinstance(first, str)
    assert isinstance(second, str)
    uuid.UUID(first)
    uuid.UUID(second)
    assert first != second


def test_scenario_status_values_match_contract() -> None:
    assert ScenarioStatus.PENDING.value == "pending"
    assert ScenarioStatus.SUBMITTED.value == "submitted"
    assert ScenarioStatus.RUNNING.value == "running"
    assert ScenarioStatus.COMPLETED.value == "completed"
    assert ScenarioStatus.FAILED.value == "failed"
    assert ScenarioStatus.CANCELLED.value == "cancelled"
