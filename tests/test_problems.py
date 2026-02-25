from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, Field

from fk_quant_research_accel.problems.black_scholes import BlackScholesParams, BlackScholesSpec
from fk_quant_research_accel.problems.harmonic_oscillator import (
    HarmonicOscillatorParams,
    HarmonicOscillatorSpec,
)
from fk_quant_research_accel.problems import (
    BaseProblemSpec as ExportedBaseProblemSpec,
    ProblemParams as ExportedProblemParams,
    ProblemSpec as ExportedProblemSpec,
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


def test_package_exports_protocol_types() -> None:
    assert ExportedProblemSpec is ProblemSpec
    assert ExportedBaseProblemSpec is BaseProblemSpec
    assert ExportedProblemParams is ProblemParams


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
    assert list_problem_ids() == ["a", "black_scholes", "harmonic_oscillator", "z"]


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


def test_black_scholes_generate_scenarios_scalar_correlations() -> None:
    spec = BlackScholesSpec()
    scenarios = spec.generate_scenarios(
        {
            "dimensions": [2, 5],
            "volatilities": [0.2],
            "correlations": [0.3],
            "option_types": ["call"],
        },
        [{"architecture": "default"}],
    )

    assert len(scenarios) == 2
    assert scenarios[0]["dim"] == 2
    assert scenarios[1]["dim"] == 5
    assert scenarios[0]["model_config"] == {"architecture": "default"}


def test_black_scholes_generate_scenarios_matrix_correlation() -> None:
    spec = BlackScholesSpec()
    correlation = [
        [0.3, 0.1, 0.2],
        [0.1, 0.3, 0.15],
        [0.2, 0.15, 0.3],
    ]
    scenarios = spec.generate_scenarios(
        {
            "dimensions": [3],
            "volatilities": [0.15],
            "correlations": correlation,
            "option_types": ["call"],
        },
        [{"architecture": "default"}],
    )

    assert len(scenarios) == 1
    assert scenarios[0]["correlation"] == correlation


def test_black_scholes_validate_valid_params() -> None:
    spec = BlackScholesSpec()
    errors = spec.validate(
        {
            "dim": 5,
            "volatility": 0.2,
            "correlation": 0.3,
            "option_type": "call",
        }
    )
    assert errors == []


def test_black_scholes_validate_invalid_params() -> None:
    spec = BlackScholesSpec()
    errors = spec.validate(
        {
            "dim": 0,
            "volatility": -1.0,
            "correlation": 0.3,
            "option_type": "call",
        }
    )
    assert errors


def test_black_scholes_validate_uses_domain_constraints() -> None:
    spec = BlackScholesSpec()
    errors = spec.validate(
        {
            "dim": 1,
            "volatility": 0.2,
            "correlation": 0.0,
            "option_type": "basket",
        }
    )
    assert any("dim >= 2" in error for error in errors)


def test_black_scholes_default_scorer_uses_train_loss() -> None:
    spec = BlackScholesSpec()
    assert spec.default_scorer({"status": "completed", "train_loss": 0.05}) == 0.05


def test_harmonic_oscillator_generate_scenarios_cross_product() -> None:
    spec = HarmonicOscillatorSpec()
    scenarios = spec.generate_scenarios(
        {
            "dimensions": [1, 2],
            "omegas": [0.5, 1.0],
            "masses": [1.0],
            "potential_types": ["quadratic"],
        },
        [{"architecture": "default"}],
    )

    assert len(scenarios) == 4
    assert {scenario["dim"] for scenario in scenarios} == {1, 2}
    assert {scenario["omega"] for scenario in scenarios} == {0.5, 1.0}


def test_harmonic_oscillator_validate_valid_params() -> None:
    spec = HarmonicOscillatorSpec()
    errors = spec.validate(
        {
            "dim": 1,
            "omega": 1.0,
            "mass": 1.0,
            "potential_type": "quadratic",
        }
    )
    assert errors == []


def test_harmonic_oscillator_validate_invalid_params() -> None:
    spec = HarmonicOscillatorSpec()
    errors = spec.validate(
        {
            "dim": 0,
            "omega": 0,
            "mass": -1,
            "potential_type": "quadratic",
        }
    )
    assert errors


def test_get_problem_spec_returns_black_scholes_builtin() -> None:
    spec = get_problem_spec("black_scholes")
    assert isinstance(spec, BlackScholesSpec)


def test_get_problem_spec_returns_harmonic_oscillator_builtin() -> None:
    spec = get_problem_spec("harmonic_oscillator")
    assert isinstance(spec, HarmonicOscillatorSpec)


def test_list_problem_ids_returns_builtin_ids() -> None:
    assert list_problem_ids() == ["black_scholes", "harmonic_oscillator"]
