"""Researcher-facing experiment manifest schema."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
import yaml


class ScenarioGridConfig(BaseModel, frozen=True):
    dimensions: list[int] = Field(min_length=1)
    volatilities: list[float] = Field(min_length=1)
    correlations: list[float] | list[list[float]] = Field(min_length=1)
    option_types: list[str] = Field(default_factory=lambda: ["call"])


class ModelSweepConfig(BaseModel, frozen=True):
    architectures: list[str] = Field(default_factory=lambda: ["default"])
    hidden_sizes: list[list[int]] | None = None
    activations: list[str] | None = None
    optimizers: list[str] | None = None


class BatchRunConfig(BaseModel, frozen=True):
    n_steps: int = Field(default=40, gt=0)
    batch_size: int = Field(default=64, gt=0)
    n_mc_paths: int = Field(default=256, gt=0)
    learning_rate: float = Field(default=1e-3, gt=0.0)
    poll_seconds: float = Field(default=1.5, gt=0.0)
    max_wait_seconds: float = Field(default=1800.0, gt=0.0)


class ScoringConfig(BaseModel, frozen=True):
    strategy: str = "loss_based"
    grad_norm_weight: float = Field(default=0.01, ge=0.0)


class OutputConfig(BaseModel, frozen=True):
    artifacts_dir: str = "artifacts"
    db_path: str | None = None


class ExperimentManifest(BaseModel, frozen=True):
    manifest_version: int = 1
    name: str | None = None
    description: str | None = None
    problem_id: str = "black_scholes"
    backend_url: str
    seed: int | None = None
    scenario_grid: ScenarioGridConfig
    model_sweep: ModelSweepConfig = Field(default_factory=ModelSweepConfig)
    batch_config: BatchRunConfig = Field(default_factory=BatchRunConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


def load_manifest(path: str | Path) -> ExperimentManifest:
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    return ExperimentManifest.model_validate(raw)
