"""Pydantic schemas for model package manifests and validation metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PackageMetrics(BaseModel, frozen=True):
    train_loss: float | None = None
    val_loss: float | None = None
    grad_norm: float | None = None
    score: float | None = None
    convergence_health: str | None = None
    progress: float | None = None


class AcceptanceResult(BaseModel, frozen=True):
    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)


class ModelPackageManifest(BaseModel, frozen=True):
    package_version: int = 1
    created_at: datetime
    batch_run_id: str
    scenario_run_id: str
    problem_id: str
    checkpoint_file: str | None = None
    checkpoint_sha256: str | None = None
    training_config: dict[str, Any]
    scenario_config: dict[str, Any]
    seed: int | None = None
    reproducibility: dict[str, Any]
    metrics: PackageMetrics
    acceptance: AcceptanceResult
    contents: list[str]
