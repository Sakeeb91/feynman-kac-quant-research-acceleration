"""Problem specification protocol and defaults."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class ProblemParams(BaseModel):
    """Base model for problem-specific parameters."""


@runtime_checkable
class ProblemSpec(Protocol):
    @property
    def problem_id(self) -> str:
        ...

    @property
    def param_schema(self) -> type[ProblemParams]:
        ...

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ...

    def validate(self, params: dict[str, Any]) -> list[str]:
        ...

    def default_scorer(self, record: dict[str, Any]) -> float:
        ...

    def default_pareto_objectives(self) -> list[str]:
        ...

    def supports_scoring_strategy(self, strategy: str) -> bool:
        ...
