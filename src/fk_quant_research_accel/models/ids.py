"""Identifier types for batch and scenario runs."""

from __future__ import annotations

import uuid
from typing import NewType


BatchRunId = NewType("BatchRunId", str)
ScenarioRunId = NewType("ScenarioRunId", str)


def generate_batch_run_id() -> BatchRunId:
    return BatchRunId(str(uuid.uuid4()))


def generate_scenario_run_id() -> ScenarioRunId:
    return ScenarioRunId(str(uuid.uuid4()))
