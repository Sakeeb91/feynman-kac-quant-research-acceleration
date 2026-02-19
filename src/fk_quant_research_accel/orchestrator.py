"""Scenario generation and batch execution for quant experiments."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from .client import FKPinnClient
from .reporting import compute_score


@dataclass(frozen=True)
class Scenario:
    dim: int
    volatility: float
    correlation: float
    option_type: str = "call"

    def as_parameters(self) -> dict[str, Any]:
        return {
            "dim": self.dim,
            "volatility": self.volatility,
            "correlation": self.correlation,
            "option_type": self.option_type,
        }


@dataclass(frozen=True)
class BatchConfig:
    n_steps: int = 40
    batch_size: int = 64
    n_mc_paths: int = 256
    learning_rate: float = 1e-3

    def to_payload(self) -> dict[str, Any]:
        return {
            "n_steps": self.n_steps,
            "batch_size": self.batch_size,
            "n_mc_paths": self.n_mc_paths,
            "learning_rate": self.learning_rate,
        }


def generate_black_scholes_scenarios(
    dimensions: list[int],
    volatilities: list[float],
    correlations: list[float],
    option_types: list[str] | None = None,
) -> list[Scenario]:
    if option_types is None:
        option_types = ["call"]
    scenarios = [
        Scenario(dim=d, volatility=v, correlation=c, option_type=o)
        for d, v, c, o in itertools.product(dimensions, volatilities, correlations, option_types)
    ]
    return scenarios


def run_batch(
    client: FKPinnClient,
    scenarios: list[Scenario],
    batch_config: BatchConfig,
    poll_seconds: float = 1.5,
    max_wait_seconds: float = 1800.0,
) -> list[dict[str, Any]]:
    """Submit all scenarios and collect terminal results."""
    submitted: list[tuple[Scenario, str]] = []
    records: list[dict[str, Any]] = []

    for scenario in scenarios:
        simulation = client.create_simulation(
            problem_id="black_scholes",
            parameters=scenario.as_parameters(),
            training_config=batch_config.to_payload(),
        )
        submitted.append((scenario, simulation["id"]))

    for scenario, simulation_id in submitted:
        simulation = client.wait_until_terminal(
            simulation_id=simulation_id,
            poll_seconds=poll_seconds,
            max_wait_seconds=max_wait_seconds,
        )
        result_envelope = client.get_result(simulation_id)
        result = result_envelope["item"]

        metrics = result.get("metrics") or {}
        record = {
            "simulation_id": simulation_id,
            "status": simulation["status"],
            "dim": scenario.dim,
            "volatility": scenario.volatility,
            "correlation": scenario.correlation,
            "option_type": scenario.option_type,
            "progress": result.get("progress", 0.0),
            "train_loss": metrics.get("loss", metrics.get("train_loss")),
            "val_loss": metrics.get("val_loss"),
            "lr": metrics.get("lr"),
            "grad_norm": metrics.get("grad_norm"),
        }
        record["score"] = compute_score(record)
        records.append(record)

    return sorted(records, key=lambda row: row["score"])
