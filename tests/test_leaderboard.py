from __future__ import annotations

from io import StringIO

from rich.console import Console

from fk_quant_research_accel.leaderboard import _format_corr
from fk_quant_research_accel.leaderboard import _format_health
from fk_quant_research_accel.leaderboard import _format_score
from fk_quant_research_accel.leaderboard import render_leaderboard


def _records() -> list[dict[str, object]]:
    return [
        {
            "score": 0.1,
            "convergence_health": "healthy",
            "dim": 5,
            "volatility": 0.2,
            "correlation": 0.0,
            "option_type": "call",
            "train_loss": 0.1,
            "status": "completed",
        },
        {
            "score": 0.2,
            "convergence_health": "oscillating",
            "dim": 10,
            "volatility": 0.3,
            "correlation": 0.1,
            "option_type": "put",
            "train_loss": 0.15,
            "status": "completed",
        },
        {
            "score": 0.3,
            "convergence_health": "stagnating",
            "dim": 20,
            "volatility": 0.4,
            "correlation": [[1.0, 0.3], [0.3, 1.0]],
            "option_type": "basket_call",
            "train_loss": 0.2,
            "status": "failed",
        },
    ]


def test_render_leaderboard_basic() -> None:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None)

    render_leaderboard(_records(), console=console)

    output = buffer.getvalue()
    assert "Leaderboard" in output
    assert "Top 3 of 3" in output


def test_render_leaderboard_empty() -> None:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None)

    render_leaderboard([], console=console)

    output = buffer.getvalue()
    assert "Top 0 of 0" in output


def test_render_leaderboard_health_colors() -> None:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None)

    render_leaderboard(_records(), console=console)

    output = buffer.getvalue()
    assert "healthy" in output
    assert "oscillating" in output
    assert "stagnating" in output


def test_render_leaderboard_n_limit() -> None:
    rows = _records() + [
        {
            "score": 0.4,
            "convergence_health": "exploding",
            "dim": 30,
            "volatility": 0.5,
            "correlation": 0.0,
            "option_type": "call",
            "train_loss": 0.4,
            "status": "failed",
        },
        {
            "score": 0.5,
            "convergence_health": "healthy",
            "dim": 40,
            "volatility": 0.6,
            "correlation": 0.0,
            "option_type": "call",
            "train_loss": 0.5,
            "status": "completed",
        },
    ]
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None)

    render_leaderboard(rows, n=3, console=console)

    output = buffer.getvalue()
    assert "Top 3 of 5" in output


def test_format_score_inf() -> None:
    assert _format_score(float("inf")) == "inf"


def test_format_score_none() -> None:
    assert _format_score(None) == "--"


def test_format_health_healthy() -> None:
    text = _format_health("healthy")
    assert text.plain == "healthy"
    assert text.style == "green"


def test_format_corr_matrix() -> None:
    assert _format_corr([[1.0, 0.3], [0.3, 1.0]]) == "[2x2]"
