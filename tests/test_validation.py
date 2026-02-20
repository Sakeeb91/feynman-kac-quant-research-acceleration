from __future__ import annotations

from fk_quant_research_accel.validation.constraints import (
    is_positive_semidefinite,
    validate_correlation_matrix,
    validate_volatility_range,
)


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
