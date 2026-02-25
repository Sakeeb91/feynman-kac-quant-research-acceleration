from __future__ import annotations

from fk_quant_research_accel.validation.constraints import (
    is_positive_semidefinite,
    validate_correlation_matrix,
    validate_dimension_option_compatibility,
    validate_scalar_correlations,
    validate_volatility_range,
)
from fk_quant_research_accel.validation.preflight import PreflightError, validate_manifest
from fk_quant_research_accel.models.experiment import ExperimentManifest, ScenarioGridConfig


def test_psd_identity_matrix() -> None:
    matrix = [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]

    assert is_positive_semidefinite(matrix) is True


def test_psd_valid_correlation_2x2() -> None:
    matrix = [
        [1.0, 0.5],
        [0.5, 1.0],
    ]

    assert is_positive_semidefinite(matrix) is True


def test_psd_valid_correlation_3x3() -> None:
    matrix = [
        [1.0, 0.3, 0.2],
        [0.3, 1.0, 0.4],
        [0.2, 0.4, 1.0],
    ]

    assert is_positive_semidefinite(matrix) is True


def test_psd_invalid_matrix() -> None:
    matrix = [
        [1.0, 0.99, 0.8],
        [0.99, 1.0, -0.8],
        [0.8, -0.8, 1.0],
    ]

    assert is_positive_semidefinite(matrix) is False


def test_psd_non_square_returns_false() -> None:
    matrix = [
        [1.0, 0.0],
        [0.0, 1.0],
        [0.0, 0.0],
    ]

    assert is_positive_semidefinite(matrix) is False


def test_psd_asymmetric_returns_false() -> None:
    matrix = [
        [1.0, 0.5],
        [0.3, 1.0],
    ]

    assert is_positive_semidefinite(matrix) is False


def test_psd_1x1_matrix() -> None:
    matrix = [[1.0]]

    assert is_positive_semidefinite(matrix) is True


def test_psd_negative_diagonal() -> None:
    matrix = [
        [1.0, 0.0],
        [0.0, -1.0],
    ]

    assert is_positive_semidefinite(matrix) is False


def test_validate_corr_matrix_valid() -> None:
    matrix = [
        [1.0, 0.5],
        [0.5, 1.0],
    ]

    errors = validate_correlation_matrix(matrix, expected_dim=2)

    assert errors == []


def test_validate_corr_matrix_wrong_dimension() -> None:
    matrix = [
        [1.0, 0.5],
        [0.5, 1.0],
    ]

    errors = validate_correlation_matrix(matrix, expected_dim=3)

    assert any("dimension" in error.lower() for error in errors)


def test_validate_corr_matrix_non_unit_diagonal() -> None:
    matrix = [
        [0.9, 0.1],
        [0.1, 1.0],
    ]

    errors = validate_correlation_matrix(matrix)

    assert any("diagonal" in error.lower() for error in errors)


def test_validate_corr_matrix_out_of_range() -> None:
    matrix = [
        [1.0, 1.2],
        [1.2, 1.0],
    ]

    errors = validate_correlation_matrix(matrix)

    assert any("[-1.0, 1.0]" in error for error in errors)


def test_validate_corr_matrix_not_psd() -> None:
    matrix = [
        [1.0, 0.9, 0.9],
        [0.9, 1.0, -0.9],
        [0.9, -0.9, 1.0],
    ]

    errors = validate_correlation_matrix(matrix)

    assert any("positive semi-definite" in error.lower() for error in errors)


def test_validate_corr_matrix_collects_all_errors() -> None:
    matrix = [
        [0.5, 1.2],
        [1.2, 0.5],
    ]

    errors = validate_correlation_matrix(matrix, expected_dim=3)

    assert len(errors) >= 3


def test_validate_volatility_valid() -> None:
    errors = validate_volatility_range([0.1, 0.2, 0.5])

    assert errors == []


def test_validate_volatility_zero() -> None:
    errors = validate_volatility_range([0.0])

    assert any("(0.0, 5.0]" in error for error in errors)


def test_validate_volatility_negative() -> None:
    errors = validate_volatility_range([-0.1])

    assert any("(0.0, 5.0]" in error for error in errors)


def test_validate_volatility_too_high() -> None:
    errors = validate_volatility_range([5.1])

    assert any("(0.0, 5.0]" in error for error in errors)


def test_validate_volatility_upper_bound() -> None:
    errors = validate_volatility_range([5.0])

    assert errors == []


def test_dim_option_compat_single_asset_call() -> None:
    errors = validate_dimension_option_compatibility(dim=1, option_type="call")

    assert errors == []


def test_dim_option_compat_multi_asset_call() -> None:
    errors = validate_dimension_option_compatibility(dim=5, option_type="call")

    assert errors == []


def test_dim_option_compat_basket_needs_multidim() -> None:
    errors = validate_dimension_option_compatibility(dim=1, option_type="basket")

    assert any("dim >= 2" in error for error in errors)


def test_dim_option_compat_barrier_any_dim() -> None:
    errors = validate_dimension_option_compatibility(dim=1, option_type="barrier_up_and_out")

    assert errors == []


def test_scalar_correlation_valid() -> None:
    errors = validate_scalar_correlations([0.0, 0.5, -0.5, 1.0, -1.0])

    assert errors == []


def test_scalar_correlation_out_of_range() -> None:
    errors = validate_scalar_correlations([1.5])

    assert any("[-1.0, 1.0]" in error for error in errors)


def test_scalar_correlation_below_range() -> None:
    errors = validate_scalar_correlations([-1.5])

    assert any("[-1.0, 1.0]" in error for error in errors)


def _valid_manifest() -> ExperimentManifest:
    return ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.3],
                "option_types": ["call"],
            },
        }
    )


def _manifest_with_grid(grid: ScenarioGridConfig) -> ExperimentManifest:
    return _valid_manifest().model_copy(update={"scenario_grid": grid})


def test_preflight_valid_manifest() -> None:
    errors = validate_manifest(_valid_manifest())

    assert errors == []


def test_preflight_catches_invalid_volatility() -> None:
    grid = ScenarioGridConfig.model_construct(
        dimensions=[5],
        volatilities=[0.0],
        correlations=[0.3],
        option_types=["call"],
    )
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert any(error.field == "scenario_grid.volatilities" for error in errors)


def test_preflight_catches_non_psd_correlation_matrix() -> None:
    grid = ScenarioGridConfig.model_construct(
        dimensions=[3],
        volatilities=[0.2],
        correlations=[
            [1.0, 0.9, 0.9],
            [0.9, 1.0, -0.9],
            [0.9, -0.9, 1.0],
        ],
        option_types=["call"],
    )
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert any(error.field == "scenario_grid.correlations.matrix" for error in errors)


def test_preflight_catches_matrix_dim_mismatch() -> None:
    grid = ScenarioGridConfig.model_construct(
        dimensions=[3],
        volatilities=[0.2],
        correlations=[
            [1.0, 0.5],
            [0.5, 1.0],
        ],
        option_types=["call"],
    )
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert any("dimension mismatch" in error.message.lower() for error in errors)


def test_preflight_catches_scalar_correlation_out_of_range() -> None:
    grid = ScenarioGridConfig.model_construct(
        dimensions=[5],
        volatilities=[0.2],
        correlations=[1.5],
        option_types=["call"],
    )
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert any(error.field == "scenario_grid.correlations.scalar" for error in errors)


def test_preflight_catches_dim_option_incompatibility() -> None:
    grid = ScenarioGridConfig.model_validate({
        "dimensions": [1],
        "volatilities": [0.2],
        "correlations": [0.0],
        "option_types": ["basket"],
    })
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert any(error.field == "scenario_grid.option_types" for error in errors)


def test_preflight_collects_multiple_errors() -> None:
    grid = ScenarioGridConfig.model_construct(
        dimensions=[1],
        volatilities=[0.0],
        correlations=[1.5],
        option_types=["basket"],
    )
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert len(errors) >= 3


def test_preflight_checks_cartesian_product_combinations() -> None:
    grid = ScenarioGridConfig.model_validate({
        "dimensions": [1, 5],
        "volatilities": [0.2],
        "correlations": [0.0],
        "option_types": ["basket"],
    })
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert any("dim=1" in error.message for error in errors)
    assert not any("dim=5" in error.message for error in errors)


def test_preflight_valid_scalar_correlations() -> None:
    grid = ScenarioGridConfig.model_construct(
        dimensions=[5],
        volatilities=[0.2],
        correlations=[0.0, 0.3],
        option_types=["call"],
    )
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert errors == []


def test_preflight_returns_preflight_error_objects() -> None:
    grid = ScenarioGridConfig.model_construct(
        dimensions=[1],
        volatilities=[0.0],
        correlations=[1.5],
        option_types=["basket"],
    )
    manifest = _manifest_with_grid(grid)

    errors = validate_manifest(manifest)

    assert errors
    assert all(isinstance(error, PreflightError) for error in errors)
    assert all(hasattr(error, "field") for error in errors)
    assert all(hasattr(error, "value") for error in errors)
    assert all(hasattr(error, "message") for error in errors)


def test_preflight_custom_scorer_valid() -> None:
    scoring = _valid_manifest().scoring.model_copy(update={"custom_scorer": "math.fabs"})
    manifest = _valid_manifest().model_copy(
        update={"scoring": scoring}
    )

    errors = validate_manifest(manifest)

    assert not any(error.field == "scoring.custom_scorer" for error in errors)


def test_preflight_custom_scorer_invalid_import() -> None:
    scoring = _valid_manifest().scoring.model_copy(update={"custom_scorer": "nonexistent.module.fn"})
    manifest = _valid_manifest().model_copy(
        update={"scoring": scoring}
    )

    errors = validate_manifest(manifest)

    assert any(error.field == "scoring.custom_scorer" for error in errors)
    assert any("Failed to import" in error.message for error in errors)


def test_preflight_custom_scorer_not_callable() -> None:
    scoring = _valid_manifest().scoring.model_copy(update={"custom_scorer": "math.pi"})
    manifest = _valid_manifest().model_copy(
        update={"scoring": scoring}
    )

    errors = validate_manifest(manifest)

    assert any(error.field == "scoring.custom_scorer" for error in errors)
    assert any("not callable" in error.message for error in errors)


def test_preflight_invalid_problem_id_returns_problem_error() -> None:
    manifest = _valid_manifest().model_copy(update={"problem_id": "not_a_problem"})

    errors = validate_manifest(manifest)

    assert any(error.field == "problem_id" for error in errors)
    assert any("Unknown problem_id" in error.message for error in errors)


def test_preflight_rejects_unsupported_scoring_strategy(monkeypatch) -> None:
    class _UnsupportedSpec:
        def supports_scoring_strategy(self, strategy: str) -> bool:
            del strategy
            return False

        def generate_scenarios(self, grid_config, model_configs):
            del model_configs
            return [
                {
                    "dim": grid_config["dimensions"][0],
                    "volatility": grid_config["volatilities"][0],
                    "correlation": grid_config["correlations"][0],
                    "option_type": grid_config["option_types"][0],
                }
            ]

        def validate(self, params):
            del params
            return []

    monkeypatch.setattr(
        "fk_quant_research_accel.validation.preflight.get_problem_spec",
        lambda _: _UnsupportedSpec(),
    )

    errors = validate_manifest(_valid_manifest())

    assert any(error.field == "scoring.strategy" for error in errors)
