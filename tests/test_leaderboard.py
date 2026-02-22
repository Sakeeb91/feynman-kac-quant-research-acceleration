from __future__ import annotations

from io import StringIO

from rich.console import Console

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
