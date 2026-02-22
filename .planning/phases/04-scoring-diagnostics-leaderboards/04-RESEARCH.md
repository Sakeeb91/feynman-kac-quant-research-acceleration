# Phase 4: Scoring, Diagnostics, and Leaderboards - Research

**Researched:** 2026-02-22
**Domain:** Pluggable scoring strategies, convergence health diagnostics, Pareto multi-objective ranking, Rich terminal leaderboards
**Confidence:** HIGH

## Summary

Phase 4 transforms the scoring layer from a single hardcoded `compute_score()` function into a pluggable scoring system with three built-in strategies (loss-based, convergence-rate, Pareto multi-objective), adds automated convergence health diagnostics per scenario, and enhances the leaderboard output to display both rank scores and health labels. The current system has a simple scoring function in `reporting.py` (train_loss + 0.01 * grad_norm penalty), a `ScoringStrategy` enum already defined in `enums.py` with all three required variants, and a `ScoringConfig` model in `experiment.py` with `strategy` and `grad_norm_weight` fields. The manifest schema already supports scoring strategy selection via `scoring.strategy: loss_based | convergence_rate | pareto_multi_objective`.

The phase has three distinct technical domains: (1) **Pluggable scoring** -- replacing `compute_score()` with a strategy-dispatched scorer that supports both built-in strategies and custom callables via manifest config, using a `Callable[[dict[str, Any]], float]` protocol; (2) **Convergence health diagnostics** -- analyzing final-state metrics (train_loss, grad_norm, val_loss) to classify each scenario as healthy/oscillating/stagnating/exploding, since the current system captures only terminal metrics and not training history time series; (3) **Rich leaderboard rendering** -- replacing the structlog-based `_log_top()` with a Rich Table that shows rank, score, health label, and key scenario parameters with color-coded health indicators.

A critical architectural observation: the current system captures only **final-state metrics** per scenario (train_loss, grad_norm, val_loss at completion). It does NOT capture training history over time (loss curves, gradient trajectories). The polling loop in `_submit_and_poll_scenario()` calls `get_simulation()` repeatedly but discards intermediate state. For RSLT-07/RSLT-08, convergence diagnostics must work with the available data: final train_loss magnitude, grad_norm magnitude, val_loss vs train_loss gap (overfitting signal), and optional `extra_metrics` that the backend might provide (e.g., `loss_history`, `grad_norm_history`). If the backend provides history arrays in the result envelope, use them. If not, apply heuristic rules to final-state metrics. This is a pragmatic approach that delivers value now and can be extended when time-series data becomes available.

**Primary recommendation:** Implement scoring as a registry of `Callable[[dict[str, Any]], float]` functions keyed by `ScoringStrategy` enum values, with a `get_scorer(config: ScoringConfig) -> Callable` factory function. For diagnostics, create a `ConvergenceHealth` enum (healthy/oscillating/stagnating/exploding) and a `diagnose_convergence()` function that analyzes available metrics. For the leaderboard, use Rich Table with color-coded health labels. Extend `CompletedScenarioResult` to include a `convergence_health` field. Add a `custom_scorer` field to `ScoringConfig` for user-provided Python callables (dotted import path string). No new dependencies required -- all existing stack (Pydantic v2, Rich, structlog) already supports this.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| Pydantic | >=2.12.5 (installed) | Extend result schemas with convergence_health field, ScoringConfig validation | Already in use. `frozen=True` models, `Literal` types for health enum, `Field()` constraints. | HIGH |
| Rich | >=14.2.0 (installed) | Leaderboard table rendering with colored health labels | Already a dependency (used by Typer). `Table`, `Console`, `Text` with style= for conditional coloring. | HIGH |
| typing (stdlib) | Python stdlib | `Callable`, `Protocol` types for scorer interface | `Callable[[dict[str, Any]], float]` for scorer type. No external dependency. | HIGH |
| importlib (stdlib) | Python stdlib | Dynamic import of custom scorer functions from dotted path strings | `importlib.import_module()` for loading user-provided scorer callables from manifest config. | HIGH |
| statistics (stdlib) | Python stdlib | Rolling window statistics for convergence diagnostics | `statistics.stdev()`, `statistics.mean()` for analyzing metric arrays when available. | HIGH |

### Supporting

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| structlog | >=25.5.0 (installed) | Log scoring decisions and diagnostic results | Log which scorer was selected, health classifications, Pareto front details. | HIGH |
| Typer | >=0.21.0 (installed) | No CLI changes needed for this phase | Leaderboard rendering happens inside existing `run-batch` / `resume-batch` commands. | HIGH |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Simple `Callable` type for scorers | Abstract base class / Protocol | ABC adds ceremony for a single-method interface. `Callable[[dict, ...], float]` is simpler and Pythonic. Protocol class would be overkill for a function signature. |
| Pure-Python Pareto dominance check | pymoo / DEAP / pareto.py library | These are full optimization frameworks (pymoo: 50MB+, DEAP: significant). Our Pareto scoring only needs non-dominated sorting on 2-3 objectives for <200 scenarios. A 20-line pure-Python implementation is sufficient and avoids adding a heavy dependency. |
| `importlib.import_module()` for custom scorers | `entry_points` / pkg_resources plugin system | Entry points require packaging and installation of the custom scorer. Dotted import path string is simpler for a solo researcher who can `pip install -e .` their scorer package or drop a .py file on `PYTHONPATH`. |
| Heuristic-based diagnostics on final metrics | Full time-series analysis with training history | Time-series analysis requires capturing intermediate metrics during the polling loop, which is a significant architectural change to the async orchestrator. Heuristic rules on final-state metrics + optional history arrays (if backend provides them in `extra_metrics`) is the pragmatic approach. Can be extended in a future phase. |
| Rich Table for leaderboard | Tabulate / prettytable / simple CSV | Rich is already installed (Typer depends on it). Its `Table` supports per-cell styling, conditional coloring, and integrates with `Console` for stderr/stdout control. No new dependency. |

**Installation:**

No new dependencies required. All libraries are already installed from Phases 1-3.

## Architecture Patterns

### Recommended Project Structure (Phase 4 additions)

```
src/fk_quant_research_accel/
    scoring/                    # NEW: pluggable scoring module
        __init__.py             # Public exports: get_scorer, SCORER_REGISTRY
        scorers.py              # Built-in scorer implementations
        pareto.py               # Pareto non-dominated sorting (pure Python)
        registry.py             # Scorer registry and factory function
    diagnostics/                # NEW: convergence health diagnostics
        __init__.py             # Public exports: diagnose_convergence, ConvergenceHealth
        health.py               # Health classification logic
    leaderboard.py              # NEW: Rich Table leaderboard renderer
    models/
        enums.py                # Extended: ConvergenceHealth enum
        result.py               # Extended: convergence_health field on CompletedScenarioResult
        experiment.py           # Extended: ScoringConfig.custom_scorer field
    reporting.py                # Modified: compute_score() delegates to scoring module
    orchestrator.py             # Modified: attach convergence_health to records
    async_orchestrator.py       # Modified: attach convergence_health to records
    cli.py                      # Modified: _log_top() uses Rich leaderboard
```

### Pattern 1: Scorer Registry with Callable Interface

**What:** A registry that maps `ScoringStrategy` enum values to scorer callables. Each scorer takes a record dict and returns a float score (lower is better). The registry provides a factory function that returns the appropriate scorer based on `ScoringConfig`.

**When to use:** Every time a scenario result needs to be scored (in both sync and async orchestrators).

**Example:**

```python
# Source: Python Strategy pattern with callables (refactoring.guru, adapted)
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..models.enums import ScoringStrategy
from ..models.experiment import ScoringConfig

# Type alias for scorer callables
ScorerFn = Callable[[dict[str, Any]], float]

# Registry: maps strategy enum -> scorer function
_SCORER_REGISTRY: dict[ScoringStrategy, ScorerFn] = {}


def register_scorer(strategy: ScoringStrategy) -> Callable[[ScorerFn], ScorerFn]:
    """Decorator to register a scorer function for a strategy."""
    def decorator(fn: ScorerFn) -> ScorerFn:
        _SCORER_REGISTRY[strategy] = fn
        return fn
    return decorator


def get_scorer(config: ScoringConfig) -> ScorerFn:
    """Return the scorer function for the given config.

    If config.custom_scorer is set, imports and returns the custom callable.
    Otherwise, looks up the built-in scorer by strategy enum.
    """
    if config.custom_scorer is not None:
        return _import_custom_scorer(config.custom_scorer)
    scorer = _SCORER_REGISTRY.get(config.strategy)
    if scorer is None:
        raise ValueError(f"No scorer registered for strategy: {config.strategy}")
    return scorer


def _import_custom_scorer(dotted_path: str) -> ScorerFn:
    """Import a scorer function from a dotted module path.

    Example: 'my_package.scorers.custom_score'
    """
    import importlib
    module_path, _, func_name = dotted_path.rpartition(".")
    if not module_path or not func_name:
        raise ValueError(
            f"custom_scorer must be a dotted path like 'pkg.module.func', got: {dotted_path!r}"
        )
    module = importlib.import_module(module_path)
    func = getattr(module, func_name, None)
    if func is None:
        raise ValueError(f"Function '{func_name}' not found in module '{module_path}'")
    if not callable(func):
        raise ValueError(f"'{dotted_path}' is not callable")
    return func
```

### Pattern 2: Built-In Scorer Implementations

**What:** Three built-in scorers matching RSLT-06: loss-based (current behavior), convergence-rate-based, and Pareto multi-objective. Each is a pure function registered via the decorator.

**When to use:** Default scoring when no custom scorer is provided.

**Example:**

```python
# scorers.py
from __future__ import annotations

from typing import Any

from ..models.enums import ScoringStrategy
from .registry import register_scorer


@register_scorer(ScoringStrategy.LOSS_BASED)
def score_loss_based(record: dict[str, Any], *, grad_norm_weight: float = 0.01) -> float:
    """Lower is better. Penalize missing values and unstable gradients.

    This is the existing compute_score() logic, extracted into the registry.
    """
    if record.get("status") != "completed":
        return float("inf")
    train_loss = record.get("train_loss")
    if train_loss is None:
        return float("inf")
    grad_norm = record.get("grad_norm")
    grad_penalty = 0.0 if grad_norm is None else abs(float(grad_norm)) * grad_norm_weight
    return float(train_loss) + grad_penalty


@register_scorer(ScoringStrategy.CONVERGENCE_RATE)
def score_convergence_rate(record: dict[str, Any]) -> float:
    """Score based on how efficiently the model converged.

    Lower is better. Uses train_loss normalized by runtime_seconds.
    Fast convergence to low loss is rewarded.
    """
    if record.get("status") != "completed":
        return float("inf")
    train_loss = record.get("train_loss")
    if train_loss is None:
        return float("inf")
    runtime = record.get("runtime_seconds") or record.get("progress", 1.0)
    if runtime is None or runtime <= 0:
        runtime = 1.0
    # Score = loss * log(1 + runtime) -- penalizes both high loss and slow convergence
    import math
    return float(train_loss) * math.log1p(float(runtime))


@register_scorer(ScoringStrategy.PARETO_MULTI_OBJECTIVE)
def score_pareto_multi_objective(record: dict[str, Any]) -> float:
    """Placeholder per-record scorer for Pareto strategy.

    The actual Pareto ranking is applied post-hoc to the full result set.
    This per-record scorer returns train_loss as the primary objective;
    the Pareto front computation happens in a separate function that
    re-ranks all records after individual scoring.
    """
    if record.get("status") != "completed":
        return float("inf")
    train_loss = record.get("train_loss")
    if train_loss is None:
        return float("inf")
    return float(train_loss)
```

### Pattern 3: Pure-Python Pareto Non-Dominated Sorting

**What:** Compute Pareto fronts for multi-objective ranking. Records on front 0 (non-dominated) get the lowest scores, front 1 gets higher scores, etc. Objectives: minimize train_loss, minimize grad_norm, minimize runtime_seconds.

**When to use:** When `scoring.strategy: pareto_multi_objective` is selected.

**Example:**

```python
# pareto.py -- pure Python, no external dependencies
from __future__ import annotations

from typing import Any


def dominates(a: list[float], b: list[float]) -> bool:
    """Return True if a Pareto-dominates b (all objectives <= and at least one <)."""
    all_leq = all(ai <= bi for ai, bi in zip(a, b))
    any_lt = any(ai < bi for ai, bi in zip(a, b))
    return all_leq and any_lt


def non_dominated_sort(
    records: list[dict[str, Any]],
    objectives: list[str],
) -> list[list[int]]:
    """Sort records into Pareto fronts. Returns list of fronts (each a list of indices).

    Front 0 = non-dominated set. Front 1 = dominated only by front 0. Etc.
    Records with missing objectives are placed in the last front.
    """
    n = len(records)
    obj_values: list[list[float]] = []
    valid_indices: list[int] = []
    invalid_indices: list[int] = []

    for i, record in enumerate(records):
        values = []
        valid = True
        for obj in objectives:
            val = record.get(obj)
            if val is None or record.get("status") != "completed":
                valid = False
                break
            values.append(float(val))
        if valid:
            obj_values.append(values)
            valid_indices.append(i)
        else:
            invalid_indices.append(i)

    # Compute domination counts and dominated sets
    dominated_by_count = [0] * len(valid_indices)
    dominates_set: list[list[int]] = [[] for _ in range(len(valid_indices))]
    fronts: list[list[int]] = []

    for i in range(len(valid_indices)):
        for j in range(i + 1, len(valid_indices)):
            if dominates(obj_values[i], obj_values[j]):
                dominates_set[i].append(j)
                dominated_by_count[j] += 1
            elif dominates(obj_values[j], obj_values[i]):
                dominates_set[j].append(i)
                dominated_by_count[i] += 1

    # Front 0: non-dominated
    current_front = [i for i, count in enumerate(dominated_by_count) if count == 0]
    while current_front:
        fronts.append([valid_indices[i] for i in current_front])
        next_front = []
        for i in current_front:
            for j in dominates_set[i]:
                dominated_by_count[j] -= 1
                if dominated_by_count[j] == 0:
                    next_front.append(j)
        current_front = next_front

    # Invalid records go in the last front
    if invalid_indices:
        fronts.append(invalid_indices)

    return fronts


def assign_pareto_scores(
    records: list[dict[str, Any]],
    objectives: list[str] | None = None,
) -> list[float]:
    """Assign Pareto-based scores to records. Lower front = lower score.

    Within a front, records are ordered by the first objective.
    """
    if objectives is None:
        objectives = ["train_loss", "grad_norm"]

    fronts = non_dominated_sort(records, objectives)
    scores = [float("inf")] * len(records)

    for front_rank, front_indices in enumerate(fronts):
        for position, idx in enumerate(front_indices):
            # Score = front_rank + fractional position within front
            scores[idx] = float(front_rank) + position / max(len(front_indices), 1)

    return scores
```

### Pattern 4: Convergence Health Diagnostics

**What:** Classify each completed scenario's convergence health as healthy/oscillating/stagnating/exploding based on available metrics. Works with both final-state metrics (always available) and optional training history arrays (when backend provides them in extra_metrics).

**When to use:** After scoring, before leaderboard rendering.

**Design rationale:** The current system captures only terminal metrics. The backend's result envelope might contain `loss_history` or `grad_norm_history` arrays in `extra_metrics`, but this is not guaranteed. The diagnostics must work without history data using heuristic rules on final-state metrics, and produce better classifications when history data is available.

**Example:**

```python
# diagnostics/health.py
from __future__ import annotations

from typing import Any

from ..models.enums import ConvergenceHealth


# Thresholds (configurable via future ScoringConfig extension)
GRAD_NORM_EXPLODING_THRESHOLD = 1e6
GRAD_NORM_HEALTHY_THRESHOLD = 10.0
LOSS_STAGNATION_THRESHOLD = 1.0
LOSS_HEALTHY_THRESHOLD = 0.1


def diagnose_convergence(record: dict[str, Any]) -> ConvergenceHealth:
    """Classify convergence health of a completed scenario.

    Uses heuristic rules on final-state metrics:
    - exploding: grad_norm exceeds threshold, or train_loss is NaN/inf
    - oscillating: val_loss >> train_loss (overfitting signal), or
                   loss_history has high variance (if available)
    - stagnating: train_loss is high and grad_norm is very small (flat region)
    - healthy: low train_loss, moderate grad_norm

    When extra_metrics contains loss_history/grad_norm_history arrays,
    uses time-series analysis for more accurate classification.
    """
    status = record.get("status")
    if status != "completed":
        return ConvergenceHealth.EXPLODING  # failed = worst case

    train_loss = record.get("train_loss")
    grad_norm = record.get("grad_norm")
    val_loss = record.get("val_loss")
    extra = record.get("extra_metrics") or {}

    # Check for NaN/inf -- exploding
    if train_loss is not None and (
        not _is_finite(train_loss) or float(train_loss) < 0
    ):
        return ConvergenceHealth.EXPLODING

    if grad_norm is not None and not _is_finite(grad_norm):
        return ConvergenceHealth.EXPLODING

    # Try time-series analysis if history is available
    loss_history = extra.get("loss_history")
    grad_history = extra.get("grad_norm_history")
    if loss_history and isinstance(loss_history, list) and len(loss_history) >= 5:
        return _diagnose_from_history(loss_history, grad_history)

    # Fall back to final-state heuristics
    return _diagnose_from_final_state(train_loss, grad_norm, val_loss)


def _is_finite(value: Any) -> bool:
    """Check if a numeric value is finite."""
    import math
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _diagnose_from_history(
    loss_history: list[float],
    grad_history: list[float] | None,
) -> ConvergenceHealth:
    """Diagnose from training history arrays."""
    import statistics

    # Check for explosion: any NaN/inf or massive spikes
    if any(not _is_finite(v) for v in loss_history):
        return ConvergenceHealth.EXPLODING

    last_n = loss_history[-5:]
    mean_last = statistics.mean(last_n)
    first_n = loss_history[:5]
    mean_first = statistics.mean(first_n)

    # Stagnation: loss barely changed
    if len(loss_history) > 10:
        relative_change = abs(mean_first - mean_last) / max(abs(mean_first), 1e-10)
        if relative_change < 0.01:  # less than 1% change
            return ConvergenceHealth.STAGNATING

    # Oscillation: high variance in recent window
    if len(last_n) >= 3:
        try:
            cv = statistics.stdev(last_n) / max(abs(mean_last), 1e-10)
            if cv > 0.5:  # coefficient of variation > 50%
                return ConvergenceHealth.OSCILLATING
        except statistics.StatisticsError:
            pass

    # Check grad explosion from history
    if grad_history and any(
        _is_finite(g) and abs(float(g)) > GRAD_NORM_EXPLODING_THRESHOLD
        for g in grad_history
    ):
        return ConvergenceHealth.EXPLODING

    return ConvergenceHealth.HEALTHY


def _diagnose_from_final_state(
    train_loss: float | None,
    grad_norm: float | None,
    val_loss: float | None,
) -> ConvergenceHealth:
    """Diagnose from final-state metrics only (no history)."""
    # Exploding: extreme grad_norm
    if grad_norm is not None and abs(float(grad_norm)) > GRAD_NORM_EXPLODING_THRESHOLD:
        return ConvergenceHealth.EXPLODING

    # Stagnating: high loss with very small gradient (stuck in flat region)
    if (
        train_loss is not None
        and float(train_loss) > LOSS_STAGNATION_THRESHOLD
        and grad_norm is not None
        and abs(float(grad_norm)) < 1e-6
    ):
        return ConvergenceHealth.STAGNATING

    # Oscillating: val_loss >> train_loss (overfitting signal)
    if (
        val_loss is not None
        and train_loss is not None
        and float(train_loss) > 0
    ):
        gap_ratio = float(val_loss) / float(train_loss)
        if gap_ratio > 3.0:  # val_loss is 3x+ train_loss
            return ConvergenceHealth.OSCILLATING

    # Oscillating: grad_norm is large relative to loss
    if (
        grad_norm is not None
        and train_loss is not None
        and float(train_loss) > 0
        and abs(float(grad_norm)) > GRAD_NORM_HEALTHY_THRESHOLD
    ):
        return ConvergenceHealth.OSCILLATING

    # Healthy: low loss, reasonable gradient
    return ConvergenceHealth.HEALTHY
```

### Pattern 5: Rich Leaderboard Table Rendering

**What:** Replace the structlog-based `_log_top()` function with a Rich Table that displays rank, score, convergence health label, and key scenario parameters. Health labels are color-coded (green for healthy, yellow for oscillating/stagnating, red for exploding).

**When to use:** At the end of batch execution, in the CLI output.

**Example:**

```python
# leaderboard.py
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models.enums import ConvergenceHealth

# Health label styling
_HEALTH_STYLES: dict[str, str] = {
    ConvergenceHealth.HEALTHY.value: "green",
    ConvergenceHealth.OSCILLATING.value: "yellow",
    ConvergenceHealth.STAGNATING.value: "yellow",
    ConvergenceHealth.EXPLODING.value: "red",
}


def render_leaderboard(
    records: list[dict[str, Any]],
    n: int = 10,
    title: str = "Leaderboard",
    console: Console | None = None,
) -> None:
    """Render a ranked leaderboard table to the terminal.

    Displays rank, score, convergence health, and key scenario parameters.
    Health labels are color-coded for at-a-glance assessment.
    """
    if console is None:
        console = Console(stderr=True)

    table = Table(title=title, caption=f"Top {min(n, len(records))} of {len(records)} scenarios")

    table.add_column("Rank", justify="right", style="bold", width=6)
    table.add_column("Score", justify="right", style="cyan", width=12)
    table.add_column("Health", justify="center", width=12)
    table.add_column("Dim", justify="right", width=5)
    table.add_column("Vol", justify="right", width=8)
    table.add_column("Corr", justify="right", width=8)
    table.add_column("Type", width=10)
    table.add_column("Loss", justify="right", width=12)
    table.add_column("Status", justify="center", width=10)

    for idx, row in enumerate(records[:n]):
        rank = str(idx + 1)
        score = _format_score(row.get("score"))
        health = _format_health(row.get("convergence_health"))
        dim = str(row.get("dim", "?"))
        vol = f"{row.get('volatility', 0.0):.3f}"
        corr = _format_corr(row.get("correlation"))
        opt_type = str(row.get("option_type", "?"))
        loss = _format_score(row.get("train_loss"))
        status = str(row.get("status", "?"))

        table.add_row(rank, score, health, dim, vol, corr, opt_type, loss, status)

    console.print(table)


def _format_score(value: Any) -> str:
    """Format a score/loss value for display."""
    if value is None:
        return "--"
    try:
        f = float(value)
        if f == float("inf"):
            return "inf"
        return f"{f:.6f}"
    except (TypeError, ValueError):
        return str(value)


def _format_health(health: str | None) -> Text:
    """Format a health label with color styling."""
    if health is None:
        return Text("--", style="dim")
    style = _HEALTH_STYLES.get(health, "dim")
    return Text(health, style=style)


def _format_corr(value: Any) -> str:
    """Format correlation value (scalar or matrix indicator)."""
    if value is None:
        return "--"
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    if isinstance(value, list):
        return f"[{len(value)}x{len(value)}]"
    return str(value)
```

### Pattern 6: Schema Extensions

**What:** Extend existing models to support convergence health and custom scorers.

**When to use:** Schema modifications happen in the first task of the phase.

**Example:**

```python
# models/enums.py -- add ConvergenceHealth enum
class ConvergenceHealth(str, Enum):
    HEALTHY = "healthy"
    OSCILLATING = "oscillating"
    STAGNATING = "stagnating"
    EXPLODING = "exploding"


# models/experiment.py -- extend ScoringConfig
class ScoringConfig(BaseModel, frozen=True):
    strategy: ScoringStrategy = ScoringStrategy.LOSS_BASED
    grad_norm_weight: float = Field(default=0.01, ge=0.0)
    custom_scorer: str | None = Field(
        default=None,
        description="Dotted import path to a custom scorer function, e.g. 'my_pkg.scorers.custom'"
    )
    pareto_objectives: list[str] = Field(
        default_factory=lambda: ["train_loss", "grad_norm"],
        description="Objective columns for Pareto multi-objective scoring"
    )


# models/result.py -- extend CompletedScenarioResult
class CompletedScenarioResult(BaseModel, frozen=True):
    # ... existing fields ...
    convergence_health: str | None = None  # ConvergenceHealth value
```

### Anti-Patterns to Avoid

- **Class-based strategy pattern for scorers:** Using ABC / abstract classes for a single-method interface is over-engineering. A `Callable[[dict, ...], float]` is sufficient and more Pythonic. Class-based strategies add boilerplate (constructor, method, registration) without benefit.
- **Adding pymoo/DEAP as dependencies for Pareto sorting:** These are full optimization frameworks (50MB+). Non-dominated sorting on <200 records with 2-3 objectives is a 30-line pure-Python function. Don't add heavy dependencies for simple operations.
- **Requiring training history for diagnostics:** The current system doesn't capture time-series data. Blocking on "we need loss curves" would delay the entire phase. Design diagnostics to work with final-state metrics (always available) and enhance when history is available (opportunistic).
- **Breaking the existing `compute_score()` contract:** Both `orchestrator.py` and `async_orchestrator.py` call `compute_score(record)`. The migration must maintain backward compatibility -- `compute_score()` should delegate to the scorer registry with a default config. This ensures existing tests and the sync orchestrator still work.
- **Putting diagnostic thresholds in the scorer:** Diagnostics (health classification) and scoring (rank computation) are separate concerns. A scenario can be healthy but have a mediocre score, or unhealthy but have a low loss. Don't couple them.
- **Hardcoding health label colors in the leaderboard:** Use a mapping dict so colors can be changed without modifying render logic. The `_HEALTH_STYLES` dict pattern is the right approach.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Scorer dispatch | Manual if/elif chain on strategy string | Registry dict + decorator pattern | Registry is extensible, testable, and avoids a growing switch statement. New scorers are added by decorating a function. |
| Pareto dominance checking | pymoo or DEAP library | Pure-Python `dominates()` + `non_dominated_sort()` (30 lines) | For <200 records with 2-3 objectives, pure Python is sufficient (<1ms). Libraries add 50MB+ for one function. |
| Terminal table rendering | Manual string formatting with f-strings | Rich `Table` | Rich handles column alignment, truncation, Unicode box characters, and per-cell styling. Manual formatting breaks on different terminal widths. |
| Dynamic function import | `eval()` or `exec()` | `importlib.import_module()` + `getattr()` | `importlib` is safe, standard, and provides clear error messages. `eval()` is a security risk. |
| Health label coloring | ANSI escape codes | Rich `Text(style=...)` | Rich handles terminal capability detection, color fallback, and integrates with Console output. Raw ANSI codes break on Windows and non-color terminals. |

**Key insight:** Phase 4 is primarily a **decomposition and enrichment** phase. The scoring logic exists but is hardcoded; it needs to be decomposed into pluggable strategies. The result schema exists but lacks health metadata; it needs enrichment. The leaderboard output exists but is plain text; it needs Rich rendering. No fundamentally new capabilities are needed -- it's restructuring and extending what's already there.

## Common Pitfalls

### Pitfall 1: Pareto Scoring Incompatible with Per-Record Score Interface

**What goes wrong:** The existing system scores records individually (`compute_score(record) -> float`), but Pareto ranking requires comparing the full set of records simultaneously. A per-record Pareto scorer can't compute front membership without seeing all other records.

**Why it happens:** Pareto dominance is inherently a multi-record operation, while the scorer interface is per-record.

**How to avoid:** The Pareto strategy uses a two-phase approach: (1) the per-record scorer returns `train_loss` as a preliminary score (so sorting still works), (2) after all records are scored, a `post_score_ranking()` function re-ranks records using Pareto fronts if the strategy is `pareto_multi_objective`. This keeps the per-record interface intact while adding a batch-level post-processing step.

**Warning signs:** Pareto-scored records all having the same rank, or Pareto rankings not reflecting actual dominance relationships.

### Pitfall 2: Convergence Diagnostics Producing False Positives Without History Data

**What goes wrong:** The heuristic rules on final-state metrics misclassify healthy scenarios. For example, a scenario with high grad_norm at the final step might actually have been converging well (the last step just happened to have a gradient spike from the sampling noise in Monte Carlo PINN training).

**Why it happens:** Final-state metrics are a snapshot, not a trajectory. One-point classification has inherently limited accuracy.

**How to avoid:** (1) Set conservative thresholds that minimize false positives (prefer "healthy" over "oscillating" when uncertain). (2) Document that health labels are indicative, not definitive. (3) Design the system so thresholds are easily tunable. (4) When training history is available in `extra_metrics`, use it for better classification. (5) Log confidence level alongside health label.

**Warning signs:** Many scenarios classified as "oscillating" or "exploding" when the researcher knows they converged fine.

### Pitfall 3: Custom Scorer Import Failing Silently

**What goes wrong:** The researcher specifies `custom_scorer: my_pkg.scorers.custom_fn` in the manifest, but the import fails at runtime (typo, missing package, wrong function signature). If this isn't caught early, all scores come back as `inf` or the batch crashes midway.

**Why it happens:** Dynamic imports are resolved at runtime, not at manifest validation time.

**How to avoid:** (1) Validate the custom scorer import at manifest load time (in pre-flight validation), before any scenarios are submitted. (2) Call the scorer with a dummy record to verify it returns a float. (3) Wrap the import in a clear error message: "Custom scorer 'my_pkg.scorers.custom_fn' could not be imported: ModuleNotFoundError..."

**Warning signs:** "All scenarios scored as inf" when using a custom scorer.

### Pitfall 4: ScoringConfig.grad_norm_weight Not Passed to Loss-Based Scorer

**What goes wrong:** The `ScoringConfig` has a `grad_norm_weight` field (default 0.01), but the scorer registry only dispatches by strategy enum. The loss-based scorer needs the weight value but the generic `Callable[[dict], float]` signature doesn't accept config.

**Why it happens:** The scorer interface is too narrow to carry config.

**How to avoid:** Use a factory pattern: `get_scorer(config: ScoringConfig) -> ScorerFn`. The factory creates a closure that captures the config. For loss-based: `lambda record: score_loss_based(record, grad_norm_weight=config.grad_norm_weight)`. This keeps the scorer callable simple while allowing config injection.

**Warning signs:** Changing `grad_norm_weight` in the manifest has no effect on scores.

### Pitfall 5: Breaking Backward Compatibility with `compute_score()` Callers

**What goes wrong:** Both `orchestrator.py` (sync) and `async_orchestrator.py` call `reporting.compute_score(record)`. Changing the function signature or behavior breaks both callers and all tests.

**Why it happens:** `compute_score()` is called from two orchestrators and tested directly.

**How to avoid:** Keep `compute_score()` as a backward-compatible wrapper that delegates to the scoring module with default config. The orchestrators should be updated to accept a `ScoringConfig` and use `get_scorer()`, but `compute_score()` remains for backward compatibility. New tests use the scoring module directly.

**Warning signs:** Existing tests breaking after Phase 4 changes.

### Pitfall 6: Rich Table Output Interfering with structlog JSON

**What goes wrong:** Rich Table writes pretty-printed output to stdout, but structlog writes JSON to stderr. If both go to the same stream, the output is garbled -- JSON lines interleaved with table box characters.

**Why it happens:** The current CLI uses `structlog.PrintLoggerFactory(file=sys.stderr)` for logging, but Rich's default Console writes to stdout.

**How to avoid:** Explicitly use `Console(stderr=True)` for the leaderboard table so it goes to the same stream as structlog. Or, better: use `Console(stderr=False)` for the table (stdout) so it can be piped/captured independently from logs (stderr). The choice depends on whether the researcher wants to pipe the leaderboard to a file. Recommend: Rich Table to **stderr** (same as logs, visible in terminal) since the CSV output goes to a file already.

**Warning signs:** Terminal output with interleaved JSON and table characters.

## Code Examples

Verified patterns from official sources:

### Rich Table with Conditional Cell Styling

```python
# Source: Rich docs (https://rich.readthedocs.io/en/stable/tables.html)
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console(stderr=True)
table = Table(title="Leaderboard")

table.add_column("Rank", justify="right", style="bold")
table.add_column("Score", justify="right", style="cyan")
table.add_column("Health", justify="center")

# Conditional styling per cell
health_value = "healthy"
health_text = Text(health_value, style="green" if health_value == "healthy" else "red")
table.add_row("1", "0.001234", health_text)

console.print(table)
```

### Pydantic Callable Field Validation

```python
# Source: Pydantic v2 docs (https://docs.pydantic.dev/2.12/api/standard_library_types)
# Pydantic validates that the field value is callable but does NOT validate
# the signature or return type. This is sufficient for our scorer interface.
from collections.abc import Callable
from pydantic import BaseModel

class ScoringConfig(BaseModel, frozen=True):
    strategy: str = "loss_based"
    custom_scorer: str | None = None  # dotted import path, validated at preflight
```

### importlib Dynamic Import

```python
# Source: Python stdlib docs (https://docs.python.org/3/library/importlib.html)
import importlib

def import_callable(dotted_path: str):
    module_path, _, attr_name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)

# Usage:
scorer = import_callable("my_package.scorers.custom_score")
result = scorer({"train_loss": 0.05, "status": "completed"})
```

### Non-Dominated Sorting (Pure Python)

```python
# Source: NSGA-II algorithm (Deb et al., 2002), simplified for our use case
# Verified against pareto.py (https://github.com/matthewjwoodruff/pareto.py)

def dominates(a: list[float], b: list[float]) -> bool:
    """a Pareto-dominates b if a[i] <= b[i] for all i and a[j] < b[j] for some j."""
    return all(ai <= bi for ai, bi in zip(a, b)) and any(ai < bi for ai, bi in zip(a, b))
```

### ConvergenceHealth Enum with Pydantic

```python
# Source: Pydantic v2 docs -- str enums work seamlessly with model_dump/model_validate
from enum import Enum

class ConvergenceHealth(str, Enum):
    HEALTHY = "healthy"
    OSCILLATING = "oscillating"
    STAGNATING = "stagnating"
    EXPLODING = "exploding"

# Usage in frozen BaseModel:
class CompletedScenarioResult(BaseModel, frozen=True):
    convergence_health: str | None = None  # Use str for JSON serialization compat
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded scoring function | Strategy pattern with callable registry | Standard Python pattern | Extensible without modifying core code |
| Manual gradient monitoring | Automated health classification | ML ops tooling (2023+) | Researchers don't need to manually inspect every run |
| Text-based leaderboard (print/log) | Rich Table with colored cells | Rich 13+ (2023) | At-a-glance assessment of run quality |
| NSGA-II from pymoo/DEAP | Pure-Python non-dominated sort | Always viable for small N | No heavy dependency for simple ranking on <200 records |
| Single-objective ranking | Multi-objective Pareto fronts | Standard MOO literature (Deb, 2002) | Researchers can optimize multiple objectives simultaneously |

**Deprecated/outdated:**
- `rich.print()` for tables: Use `Console.print(table)` for proper stderr/stdout control
- Abstract base classes for strategy pattern: `Callable` type hints are more Pythonic and simpler in modern Python (3.10+)

## Open Questions

1. **Backend Training History Availability**
   - What we know: The backend returns a result envelope with `metrics` dict containing final-state values (loss, grad_norm, val_loss, lr). The `extra_metrics` field on result schemas exists but is currently unpopulated.
   - What's unclear: Does the backend's `/api/v1/results/{id}` endpoint return `loss_history` or `grad_norm_history` arrays? Does the polling `get_simulation()` response include intermediate metrics that could be captured?
   - Recommendation: Design diagnostics to work without history data (heuristic rules on final state). If the backend provides history arrays, consume them from `extra_metrics`. Add a TODO to capture intermediate polling metrics in a future phase if needed. This is not a blocker for Phase 4.

2. **Pareto Objective Selection**
   - What we know: RSLT-06 requires "Pareto multi-objective" scoring. The natural objectives for PINN training are train_loss, grad_norm, and potentially runtime_seconds.
   - What's unclear: Which objectives should be the default? Should the researcher be able to configure objectives via manifest?
   - Recommendation: Default to `["train_loss", "grad_norm"]` as Pareto objectives. Add `pareto_objectives` field to `ScoringConfig` so the researcher can customize. Document that all objective fields must be present in the record dict.

3. **Diagnostic Threshold Tuning**
   - What we know: PINN training has specific convergence characteristics (loss landscape is non-convex, Monte Carlo sampling introduces noise, gradient norms can spike from boundary condition terms).
   - What's unclear: What are appropriate threshold values for grad_norm_exploding (1e6?), loss_stagnation (1.0?), oscillation detection (CV > 50%?)?
   - Recommendation: Start with conservative thresholds documented in constants. Make them configurable in a future phase via `DiagnosticsConfig` in the manifest. Log when a threshold is triggered so the researcher can calibrate.

4. **Convergence Health for Failed Scenarios**
   - What we know: `FailedScenarioResult` has `status: "failed"` and no metrics.
   - What's unclear: Should failed scenarios get a health label? They technically "exploded" (or encountered an error).
   - Recommendation: Failed scenarios get `convergence_health: "exploding"` by default since failure typically indicates training instability or a crash. This is consistent with the requirement that "each scenario result includes a convergence health label."

5. **Custom Scorer Validation Depth**
   - What we know: The manifest can specify `custom_scorer: "my_pkg.scorers.fn"`. At preflight, we can try to import it.
   - What's unclear: How far should validation go? Import only? Call with a dummy record? Check return type?
   - Recommendation: At preflight, attempt import and verify `callable()`. Do NOT call with a dummy record (side effects unknown). If import fails, return a `PreflightError`. This catches 90% of configuration errors (typos, missing packages) without risking side effects.

## Sources

### Primary (HIGH confidence)

- Rich Table Documentation (https://rich.readthedocs.io/en/stable/tables.html) -- Table construction, column styling, per-row and per-cell style overrides, Console(stderr=True) for output control (Context7 `/websites/rich_readthedocs_io_en_stable`)
- Pydantic v2 Callable Type Documentation (https://docs.pydantic.dev/2.12/api/standard_library_types) -- Pydantic validates `callable()` but not signature; sufficient for scorer interface (Context7 `/websites/pydantic_dev_2_12`)
- Python importlib Documentation (https://docs.python.org/3/library/importlib.html) -- `importlib.import_module()` for dynamic import of custom scorers
- Python statistics module (https://docs.python.org/3/library/statistics.html) -- `stdev()`, `mean()` for time-series diagnostics
- NSGA-II Algorithm (Deb et al., 2002) -- Non-dominated sorting for multi-objective optimization; the foundational algorithm for Pareto ranking
- pareto.py (https://github.com/matthewjwoodruff/pareto.py) -- Pure-Python epsilon-nondominated sorting reference implementation; confirmed zero-dependency approach is viable

### Secondary (MEDIUM confidence)

- Strategy Pattern in Python (https://refactoring.guru/design-patterns/strategy/python/example) -- Callable-based strategy pattern in Python; community-standard approach
- Convergence and Error Analysis of PINNs (https://hal.science/hal-04085519/document) -- PINN convergence theory; confirms loss oscillation and gradient explosion are common PINN training pathologies
- On the Convergence of PINNs (https://arxiv.org/abs/2305.01240) -- Theoretical analysis of PINN convergence; validates heuristic rules for detecting convergence failures
- Neptune.ai Gradient Monitoring Guide (https://neptune.ai/blog/monitoring-diagnosing-and-solving-gradient-issues-in-foundation-models) -- Practical heuristics for detecting gradient explosion/vanishing; grad_norm thresholds
- Machine Learning Mastery - Exploding Gradients (https://machinelearningmastery.com/exploding-gradients-in-neural-networks/) -- Heuristic detection rules: NaN/inf values, loss spikes, large weight updates
- Spot Intelligence - Exploding Gradient Detection (https://spotintelligence.com/2023/12/06/exploding-gradient-problem/) -- Threshold-based detection: grad_norm > 1e6 as explosion indicator

### Tertiary (LOW confidence)

- PINN training specifics: The exact threshold values for PINN-specific diagnostics (loss stagnation at 1.0, grad_norm explosion at 1e6) are educated guesses based on general neural network training heuristics, not PINN-specific empirical data. These should be tuned based on actual runs.
- Backend history data: The assumption that the backend might provide `loss_history` in `extra_metrics` is unverified. The diagnostics are designed to work without it.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH -- No new dependencies. Rich Table, Pydantic Callable, importlib are all well-documented and already in the project. Scorer registry pattern is standard Python.
- Architecture: HIGH -- The decomposition into scoring module, diagnostics module, and leaderboard renderer follows the existing layered architecture. The scorer registry pattern, Pareto non-dominated sorting, and Rich Table rendering are all well-established patterns with code examples verified against official documentation.
- Pitfalls: HIGH -- Pareto two-phase scoring, backward compatibility with `compute_score()`, Rich stderr routing, and custom scorer validation are all real issues with documented mitigations. The solutions are straightforward.
- Diagnostics: MEDIUM -- The heuristic rules for convergence health classification on final-state metrics are reasonable but not empirically validated against actual PINN training data. Thresholds may need tuning. The time-series path (when history is available) uses standard statistical techniques but depends on unverified backend data availability.

**Research date:** 2026-02-22
**Valid until:** 2026-03-22 (stable domain; 30-day validity)
