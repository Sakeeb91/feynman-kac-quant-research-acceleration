from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

from fk_quant_research_accel.problems.black_scholes import BlackScholesParams, BlackScholesSpec
from fk_quant_research_accel.problems.harmonic_oscillator import (
    HarmonicOscillatorParams,
    HarmonicOscillatorSpec,
)
from fk_quant_research_accel.problems.protocol import BaseProblemSpec, ProblemParams, ProblemSpec
from fk_quant_research_accel.problems.registry import (
    _PROBLEM_REGISTRY,
    get_problem_spec,
    list_problem_ids,
    register_problem,
)


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


class _Params(ProblemParams):
    dim: int = Field(gt=0)


class _BaseSpec(BaseProblemSpec):
    @property
    def problem_id(self) -> str:
        return "base"

    @property
    def param_schema(self) -> type[ProblemParams]:
        return _Params

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del grid_config, model_configs
        return []


def test_base_problem_spec_default_scorer_completed() -> None:
    spec = _BaseSpec()
    assert spec.default_scorer({"status": "completed", "train_loss": 0.2}) == 0.2


def test_base_problem_spec_default_scorer_failed_or_missing() -> None:
    spec = _BaseSpec()
    assert spec.default_scorer({"status": "failed", "train_loss": 0.2}) == float("inf")
    assert spec.default_scorer({"status": "completed", "train_loss": None}) == float("inf")


def test_base_problem_spec_default_pareto_objectives() -> None:
    spec = _BaseSpec()
    assert spec.default_pareto_objectives() == ["train_loss", "grad_norm"]


def test_base_problem_spec_supports_scoring_strategy() -> None:
    spec = _BaseSpec()
    assert spec.supports_scoring_strategy("loss_based") is True


def test_base_problem_spec_validate_uses_param_schema() -> None:
    spec = _BaseSpec()
    assert spec.validate({"dim": 1}) == []
    errors = spec.validate({"dim": 0})
    assert errors
    assert "greater than 0" in errors[0]


@pytest.fixture(autouse=True)
def _clear_problem_registry() -> None:
    _PROBLEM_REGISTRY.clear()


class _RegisteredSpec(_BaseSpec):
    @property
    def problem_id(self) -> str:
        return "registered"


def test_register_problem_and_get_problem_spec() -> None:
    spec = _RegisteredSpec()
    register_problem(spec)
    assert get_problem_spec("registered") is spec


def test_register_problem_rejects_duplicates() -> None:
    first = _RegisteredSpec()
    second = _RegisteredSpec()
    register_problem(first)
    with pytest.raises(ValueError):
        register_problem(second)


def test_list_problem_ids_sorted() -> None:
    class _A(_RegisteredSpec):
        @property
        def problem_id(self) -> str:
            return "a"

    class _Z(_RegisteredSpec):
        @property
        def problem_id(self) -> str:
            return "z"

    register_problem(_Z())
    register_problem(_A())
    assert list_problem_ids() == ["a", "z"]


def test_get_problem_spec_error_lists_valid_ids() -> None:
    register_problem(_RegisteredSpec())
    with pytest.raises(ValueError) as exc:
        get_problem_spec("missing")
    message = str(exc.value)
    assert "registered" in message


def test_get_problem_spec_error_suggests_nearest_match() -> None:
    class _BlackScholesLike(_RegisteredSpec):
        @property
        def problem_id(self) -> str:
            return "black_scholes"

    register_problem(_BlackScholesLike())
    with pytest.raises(ValueError) as exc:
        get_problem_spec("black_shoals")
    assert "Did you mean 'black_scholes'" in str(exc.value)


def test_black_scholes_spec_conforms_to_protocol() -> None:
    assert isinstance(BlackScholesSpec(), ProblemSpec)


def test_black_scholes_problem_id() -> None:
    assert BlackScholesSpec().problem_id == "black_scholes"


def test_black_scholes_param_schema() -> None:
    assert BlackScholesSpec().param_schema is BlackScholesParams


def test_harmonic_oscillator_spec_conforms_to_protocol() -> None:
    assert isinstance(HarmonicOscillatorSpec(), ProblemSpec)


def test_harmonic_oscillator_problem_id() -> None:
    assert HarmonicOscillatorSpec().problem_id == "harmonic_oscillator"


def test_harmonic_oscillator_param_schema() -> None:
    assert HarmonicOscillatorSpec().param_schema is HarmonicOscillatorParams
