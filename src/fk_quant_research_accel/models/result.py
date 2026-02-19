"""Scenario result schema persisted in SQLite and artifact files."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import ScenarioStatus


class ScenarioResult(BaseModel, frozen=True):
    scenario_run_id: str
    batch_run_id: str
    simulation_id: str | None = None
    status: ScenarioStatus
    scenario_params: dict[str, Any]
    train_loss: float | None = None
    val_loss: float | None = None
    grad_norm: float | None = None
    lr: float | None = None
    progress: float = 0.0
    score: float | None = None
    error_message: str | None = None
    checkpoint_path: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    extra_metrics: dict[str, Any] = Field(default_factory=dict)
