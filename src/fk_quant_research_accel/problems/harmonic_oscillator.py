"""Built-in harmonic oscillator problem specification."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from fk_quant_research_accel.problems.protocol import BaseProblemSpec, ProblemParams
from fk_quant_research_accel.problems.registry import register_problem


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
        del grid_config, model_configs
        return []


register_problem(HarmonicOscillatorSpec())
