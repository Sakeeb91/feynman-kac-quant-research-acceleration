"""Built-in harmonic oscillator problem specification."""

from __future__ import annotations

import itertools
from typing import Any

from pydantic import Field

from fk_quant_research_accel.problems.protocol import BaseProblemSpec, ProblemParams
from fk_quant_research_accel.problems.registry import register_problem

__all__ = ["HarmonicOscillatorParams", "HarmonicOscillatorSpec"]


class HarmonicOscillatorParams(ProblemParams):
    dim: int = Field(gt=0, le=10)
    omega: float = Field(gt=0.0, le=100.0)
    mass: float = Field(default=1.0, gt=0.0)
    potential_type: str = Field(default="quadratic")


class HarmonicOscillatorSpec(BaseProblemSpec):
    @property
    def problem_id(self) -> str:
        return "harmonic_oscillator"

    @property
    def param_schema(self) -> type[ProblemParams]:
        return HarmonicOscillatorParams

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        dimensions = list(grid_config.get("dimensions", [1]))
        omegas = list(grid_config.get("omegas", [1.0]))
        masses = list(grid_config.get("masses", [1.0]))
        potential_types = list(grid_config.get("potential_types", ["quadratic"]))

        scenarios: list[dict[str, Any]] = []
        for dim, omega, mass, potential_type, model_config in itertools.product(
            dimensions,
            omegas,
            masses,
            potential_types,
            model_configs,
        ):
            scenarios.append(
                {
                    "dim": dim,
                    "omega": omega,
                    "mass": mass,
                    "potential_type": potential_type,
                    "model_config": dict(model_config),
                }
            )
        return scenarios

    def validate(self, params: dict[str, Any]) -> list[str]:
        errors = super().validate(params)
        dim = params.get("dim")
        omega = params.get("omega")
        mass = params.get("mass")

        if isinstance(dim, int) and not (1 <= dim <= 10):
            errors.append(f"dim must be in [1, 10], got {dim}.")
        if isinstance(omega, (int, float)) and not (0.0 < float(omega) <= 100.0):
            errors.append(f"omega must be in (0.0, 100.0], got {omega}.")
        if isinstance(mass, (int, float)) and float(mass) <= 0.0:
            errors.append(f"mass must be > 0.0, got {mass}.")

        return errors


register_problem(HarmonicOscillatorSpec())
