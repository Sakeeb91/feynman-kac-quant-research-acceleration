"""Scenario result schema persisted in SQLite and artifact files."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .enums import ScenarioStatus


class ErrorStats(BaseModel, frozen=True):
    pde_residual: float | None = None
    boundary_error: float | None = None
    relative_l2_error: float | None = None


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


class CompletedScenarioResult(BaseModel, frozen=True):
    status: Literal["completed"]
    scenario_run_id: str
    batch_run_id: str
    simulation_id: str
    scenario_params: dict[str, Any]
    train_loss: float
    grad_norm: float
    runtime_seconds: float
    rank_score: float
    error_stats: ErrorStats = Field(default_factory=ErrorStats)
    val_loss: float | None = None
    lr: float | None = None
    progress: float = 1.0
    checkpoint_path: str | None = None
    extra_metrics: dict[str, Any] = Field(default_factory=dict)
