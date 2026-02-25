from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from fk_quant_research_accel.problems.protocol import ProblemParams, ProblemSpec


def test_problem_params_is_pydantic_model() -> None:
    assert issubclass(ProblemParams, BaseModel)


class _ProtocolStub:
    @property
    def problem_id(self) -> str:
        return "stub"

    @property
    def param_schema(self) -> type[ProblemParams]:
        return ProblemParams

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del grid_config, model_configs
        return []

    def validate(self, params: dict[str, Any]) -> list[str]:
        del params
        return []

    def default_scorer(self, record: dict[str, Any]) -> float:
        del record
        return 0.0

    def default_pareto_objectives(self) -> list[str]:
        return ["train_loss", "grad_norm"]

    def supports_scoring_strategy(self, strategy: str) -> bool:
        del strategy
        return True


def test_problem_spec_is_runtime_checkable_protocol() -> None:
    assert isinstance(_ProtocolStub(), ProblemSpec)
