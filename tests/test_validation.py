from __future__ import annotations

from fk_quant_research_accel.validation.constraints import is_positive_semidefinite


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
