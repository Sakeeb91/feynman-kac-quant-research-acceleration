# Phase 5: Run Analysis CLI - Research

**Researched:** 2026-02-23
**Domain:** CLI run listing, two-run comparison, single-run deep dive with Rich terminal rendering and multi-format output
**Confidence:** HIGH

## Summary

Phase 5 adds three read-only CLI commands (`list-runs`, `compare-runs`, `show-run`) that query the existing SQLite MetadataStore and render results in the terminal. No new external dependencies are required -- all capabilities come from the existing stack (Typer 0.21+, Rich 14.2+, Pydantic 2.12+, sqlite3 stdlib). The MetadataStore already persists batch_runs and scenario_runs tables with all the data these commands need, but currently lacks query methods for listing multiple runs with filters, resolving UUID prefixes, or computing aggregate metrics. The core work is (1) adding query/aggregation methods to MetadataStore, (2) building a run-resolver layer that translates user identifiers (`latest`, `latest~N`, UUID prefix) into canonical batch_run_ids, (3) building three CLI commands with Typer that produce Rich table/panel output on TTY and plain text/JSON/CSV when piped, and (4) building a comparison engine that aligns two runs by scenario parameter key and computes deltas.

The existing codebase demonstrates clear patterns for all of these. The CLI already uses `@app.command()` decorators with `typer.Option`/`typer.Argument`, the leaderboard module shows Rich Table construction with styled columns and `Console(stderr=True)`, and tests use `typer.testing.CliRunner` with monkeypatched dependencies. Phase 5 follows these patterns exactly.

A critical architectural insight: the `scenario_json` column stores the scenario parameters as JSON (e.g., `{"dim": 5, "volatility": 0.2, "correlation": 0.0, "option_type": "call"}`), matching the `Scenario.as_parameters()` output. For comparison alignment, the alignment key `(dim, volatility, correlation, option_type, model_config)` can be derived by parsing this JSON. The `result_json` column stores the full result record including `score`, `train_loss`, `grad_norm`, `progress`, `convergence_health`, and `status` -- all the metrics needed for comparison deltas and the show-run deep dive.

**Primary recommendation:** Add new query methods to MetadataStore (list_batch_runs, get_batch_run_by_prefix, get_latest_batch_runs), build a `RunResolver` helper that translates user selectors to canonical IDs, create a `run_analysis/` subpackage for formatters and comparison logic, and add three commands to the existing `cli.py` Typer app. Use `Console.is_terminal` for auto-detecting output mode. Tests should use in-memory SQLite databases with pre-populated test data.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Run identification
- Canonical ID: existing `batch_run_id` UUID from MetadataStore
- Accept unambiguous short prefix (first 8+ characters) for convenience
- Lightweight selectors: `latest` (most recent) and `latest~N` (Nth most recent run)
- No custom aliases in Phase 5 -- skip new persistence surface; defer to future phase

#### Comparison display
- Compare exactly two runs in Phase 5 (no multi-run comparison)
- Align rows by scenario parameter key: `(dim, volatility, correlation, option_type, model_config)`
- Per-row columns: `run_a` value, `run_b` value, `delta_abs`, `delta_pct` for core metrics: score, train_loss, grad_norm, progress
- Status mismatch flags when scenarios differ in completion status
- Summary block at top/bottom: matched scenario count, missing-on-each-side counts, win/loss count on score

#### Filtering & sorting
- `list-runs` filters: `--status`, `--from`, `--to`, `--min-score`, `--max-score`, `--git-sha`, `--manifest-hash`
- Default sort: newest first (`created_at DESC`)
- Pagination: `--limit` (default 20), `--offset` (default 0)
- `compare-runs` default: completed scenarios only, with `--all-status` opt-in to include failed/pending

#### Output formatting
- Auto-detect output target: Rich table on TTY, plain text when piped
- Explicit override: `--format table|json|csv`
- `--verbose` flag for dense vs compact row display
- `list-runs` default columns: run_id, created_at, status, scenario_count, completed/failed, best_score, median_score

### Claude's Discretion
- Exact Rich table styling and color palette for health labels
- Column truncation/wrapping strategy for narrow terminals
- JSON/CSV field ordering and naming conventions
- Error message formatting when run IDs are ambiguous or not found
- Whether `show-run` uses Rich panels, tables, or mixed layout

### Deferred Ideas (OUT OF SCOPE)
- Custom run aliases (e.g., `baseline`, `best-so-far`) -- requires new persistence surface, separate phase
- Multi-run comparison (3+ runs) -- Phase 5 locks at exactly two
- Export comparison reports to file (HTML/PDF) -- future enhancement
</user_constraints>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| Typer | >=0.21.0 (installed) | CLI command registration, argument/option parsing | Already used for `run-batch` and `resume-batch` commands. `@app.command()` decorator pattern, `typer.Argument`, `typer.Option`. | HIGH |
| Rich | >=14.2.0 (installed) | Terminal tables, panels, styled text, TTY detection | Already used by `leaderboard.py`. `Console.is_terminal`, `Table`, `Panel`, `Text` with style. | HIGH |
| sqlite3 | stdlib | Direct SQL queries for filtering, aggregation, pagination | MetadataStore already wraps sqlite3. New methods add WHERE/ORDER BY/LIMIT/OFFSET clauses. | HIGH |
| Pydantic | >=2.12.5 (installed) | Data models for query results, filter parameters | Already used for all domain models. `BaseModel` with `frozen=True` for typed query results. | HIGH |
| json | stdlib | Parse `scenario_json` and `result_json` columns | Already used throughout the codebase for JSON serialization/deserialization. | HIGH |
| csv | stdlib | CSV output format for piped output | Already used in `reporting.py` for CSV writing. | HIGH |
| statistics | stdlib | Median score computation for list-runs summary | `statistics.median()` for aggregate metrics. Already used in `diagnostics/health.py`. | HIGH |

### Supporting

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| structlog | >=25.5.0 (installed) | Structured logging for query operations | Log query parameters, resolver results, errors. | HIGH |
| typing | stdlib | Type annotations for resolver functions and formatters | `Literal["table", "json", "csv"]` for format enum, `NewType` for IDs. | HIGH |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw SQL in MetadataStore | SQLAlchemy ORM | ORM adds dependency and complexity. Raw SQL is fine for ~10 query methods on 2 tables. Matches existing pattern. |
| `Console.is_terminal` check | `sys.stdout.isatty()` | Rich's `Console.is_terminal` handles edge cases (Jupyter, IDLE, forced terminal). More robust. |
| `statistics.median()` | numpy/scipy | Overkill for a single median calculation on <100 floats. stdlib is sufficient. |
| Python-side JSON parsing for alignment | SQLite `json_extract()` | `json_extract()` works in SQLite 3.38+ but Python 3.10 may ship older SQLite on some platforms. Python-side parsing is safer and already the pattern used in `resume_batch_async`. |

**Installation:**

No new dependencies required. All libraries are already installed from Phases 1-4.

## Architecture Patterns

### Recommended Project Structure (Phase 5 additions)

```
src/fk_quant_research_accel/
    run_analysis/                    # NEW: run analysis subpackage
        __init__.py                  # Public exports
        resolver.py                  # RunResolver: selector -> canonical ID
        queries.py                   # Query functions on MetadataStore
        formatters.py                # Output formatting (table/json/csv)
        comparison.py                # Two-run comparison engine
    store/
        metadata.py                  # MODIFIED: add list/filter/prefix query methods
    cli.py                           # MODIFIED: add list-runs, compare-runs, show-run commands
```

### Pattern 1: Run Resolver (Selector -> Canonical ID)

**What:** A resolver function that translates user-provided identifiers (`latest`, `latest~N`, UUID, UUID prefix) into canonical `batch_run_id` strings. Returns clear error messages for ambiguous or not-found cases.

**When to use:** Every command that accepts a run identifier (`compare-runs`, `show-run`, and the `latest` / `latest~N` selectors).

**Example:**

```python
# Source: Codebase pattern from models/ids.py + store/metadata.py
import re
from typing import Literal

_LATEST_RE = re.compile(r"^latest(?:~(\d+))?$")

def resolve_run_id(
    selector: str,
    store: MetadataStore,
) -> str:
    """Resolve a user-provided selector to a canonical batch_run_id.

    Selectors:
      - Full UUID: exact match
      - 8+ character prefix: LIKE prefix match, must be unambiguous
      - "latest": most recent run (created_at DESC, LIMIT 1)
      - "latest~N": Nth most recent run (OFFSET N)

    Raises ValueError on not-found or ambiguous match.
    """
    match = _LATEST_RE.match(selector)
    if match:
        offset = int(match.group(1) or 0)
        rows = store.list_batch_runs(order_by="created_at DESC", limit=1, offset=offset)
        if not rows:
            raise ValueError(f"No run found for selector '{selector}'")
        return rows[0]["batch_run_id"]

    # Full UUID or prefix
    if len(selector) < 8:
        raise ValueError(
            f"Run ID prefix must be at least 8 characters, got {len(selector)}: '{selector}'"
        )
    matches = store.find_batch_runs_by_prefix(selector)
    if len(matches) == 0:
        raise ValueError(f"No run found matching '{selector}'")
    if len(matches) > 1:
        ids = [m["batch_run_id"] for m in matches]
        raise ValueError(
            f"Ambiguous prefix '{selector}' matches {len(matches)} runs: "
            + ", ".join(ids[:5])
        )
    return matches[0]["batch_run_id"]
```

**Confidence:** HIGH -- follows existing codebase patterns, no external dependencies.

### Pattern 2: Scenario Alignment for Comparison

**What:** Parse `scenario_json` from both runs, build a composite key `(dim, volatility, correlation, option_type, model_config)`, and align matching scenarios into pairs. Unmatched scenarios are flagged as "missing in run A" or "missing in run B".

**When to use:** `compare-runs` command.

**Example:**

```python
# Source: Derived from orchestrator.py Scenario.as_parameters() pattern
import json
from typing import Any

def _scenario_key(scenario_json: str) -> tuple:
    """Build a hashable alignment key from scenario_json.

    Matches the Cartesian product axes defined in orchestrator.py:
    (dim, volatility, correlation, option_type, model_config)
    """
    params = json.loads(scenario_json)
    # Correlation can be float or list[list[float]] -- normalize to string for hashing
    corr = params.get("correlation")
    corr_key = json.dumps(corr, sort_keys=True) if isinstance(corr, list) else corr
    model_config = params.get("model_config")
    mc_key = json.dumps(model_config, sort_keys=True) if model_config else None
    return (
        params.get("dim"),
        params.get("volatility"),
        corr_key,
        params.get("option_type"),
        mc_key,
    )


def align_scenarios(
    scenarios_a: list[dict[str, Any]],
    scenarios_b: list[dict[str, Any]],
) -> tuple[
    list[tuple[dict, dict]],       # matched pairs
    list[dict[str, Any]],           # only in A
    list[dict[str, Any]],           # only in B
]:
    """Align two sets of scenario rows by parameter key."""
    map_a = {_scenario_key(s["scenario_json"]): s for s in scenarios_a}
    map_b = {_scenario_key(s["scenario_json"]): s for s in scenarios_b}

    matched = []
    only_a = []
    only_b = []

    all_keys = set(map_a) | set(map_b)
    for key in sorted(all_keys, key=str):
        if key in map_a and key in map_b:
            matched.append((map_a[key], map_b[key]))
        elif key in map_a:
            only_a.append(map_a[key])
        else:
            only_b.append(map_b[key])

    return matched, only_a, only_b
```

**Confidence:** HIGH -- `scenario_json` structure verified in codebase (orchestrator.py line 287, async_orchestrator.py line 457).

### Pattern 3: TTY-Aware Output Formatting

**What:** Auto-detect whether stdout is a terminal and choose Rich tables vs plain text/JSON/CSV accordingly. Allow explicit override via `--format` flag.

**When to use:** All three commands.

**Example:**

```python
# Source: Rich docs Console.is_terminal, existing leaderboard.py Console(stderr=True) pattern
import json
import csv
import io
import sys
from typing import Any, Literal

from rich.console import Console

OutputFormat = Literal["table", "json", "csv"]

def get_effective_format(
    explicit_format: OutputFormat | None,
) -> OutputFormat:
    """Determine output format: explicit flag > auto-detect."""
    if explicit_format is not None:
        return explicit_format
    # Rich Console auto-detects TTY
    console = Console()
    return "table" if console.is_terminal else "json"


def emit_output(
    records: list[dict[str, Any]],
    fmt: OutputFormat,
    render_table: callable,  # function that builds and prints Rich Table
) -> None:
    if fmt == "table":
        render_table(records)
    elif fmt == "json":
        print(json.dumps(records, indent=2, default=str))
    elif fmt == "csv":
        if not records:
            return
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
        sys.stdout.write(buf.getvalue())
```

**Confidence:** HIGH -- `Console.is_terminal` verified in Rich docs (Context7). Matches existing `leaderboard.py` Console usage.

### Pattern 4: Adding Commands to Existing Typer App

**What:** Add new `@app.command()` entries to the existing `cli.py` app, following the same patterns as `run-batch` and `resume-batch`.

**When to use:** Registering `list-runs`, `compare-runs`, `show-run`.

**Example:**

```python
# Source: Existing cli.py pattern (run-batch, resume-batch)
@app.command("list-runs")
def list_runs_command(
    db_path: str = typer.Option("artifacts/experiments.db", "--db-path"),
    status: str | None = typer.Option(None, "--status"),
    from_date: str | None = typer.Option(None, "--from"),
    to_date: str | None = typer.Option(None, "--to"),
    min_score: float | None = typer.Option(None, "--min-score"),
    max_score: float | None = typer.Option(None, "--max-score"),
    git_sha: str | None = typer.Option(None, "--git-sha"),
    manifest_hash: str | None = typer.Option(None, "--manifest-hash"),
    limit: int = typer.Option(20, "--limit", min=1),
    offset: int = typer.Option(0, "--offset", min=0),
    output_format: str | None = typer.Option(None, "--format"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    ...
```

**Confidence:** HIGH -- directly mirrors existing `cli.py` command patterns.

### Anti-Patterns to Avoid

- **Querying all runs and filtering in Python:** Use SQL WHERE clauses for filtering and LIMIT/OFFSET for pagination. The DB may have hundreds of runs; querying all and filtering in Python wastes memory and is O(n).
- **Parsing `scenario_json` in SQL:** While SQLite's `json_extract()` works in newer versions, Python 3.10 may ship with older SQLite on some platforms. Parse JSON in Python after fetching rows, matching the existing pattern in `resume_batch_async`.
- **Hardcoding db_path:** All commands should accept `--db-path` with a sensible default (`artifacts/experiments.db`), matching the existing `resume-batch` pattern.
- **Mixing stdout and stderr for table output:** Follow the existing `leaderboard.py` convention of `Console(stderr=True)` for Rich output. Data output (JSON/CSV) goes to stdout so it can be piped.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TTY detection | Custom `os.isatty()` logic | `Console().is_terminal` | Rich handles edge cases (Jupyter, IDLE, Windows). |
| Table formatting | Manual string padding/alignment | `Rich.Table` | Already used in leaderboard.py. Handles Unicode width, wrapping, color. |
| CSV writing | Manual string escaping | `csv.DictWriter` | Already used in `reporting.py`. Handles quoting, escaping. |
| UUID validation | Custom regex | `len(selector) >= 8` + SQL LIKE | UUID4 format is well-defined. Prefix matching via SQL is simpler than regex validation. |
| Percentage calculation | Custom null-safe division | Helper function with None guards | Division by zero and None values are common in metrics. One helper reused everywhere. |

**Key insight:** Phase 5 is a read-only analysis layer. It queries existing data and formats it. Every building block (SQLite queries, Rich tables, CSV output, Typer commands) already has a proven pattern in the codebase. The challenge is composing them correctly, not inventing new abstractions.

## Common Pitfalls

### Pitfall 1: Ambiguous UUID Prefix Matching

**What goes wrong:** A short prefix matches multiple runs, or the user provides fewer than 8 characters, causing confusing partial matches.
**Why it happens:** UUID4 has high entropy but short prefixes (4-6 chars) can collide when there are hundreds of runs.
**How to avoid:** Enforce minimum 8-character prefix. Return clear error message listing all matching run IDs (up to 5) when ambiguous. The 8-char minimum gives ~4 billion unique prefixes, making collisions extremely unlikely for research-scale datasets (<10k runs).
**Warning signs:** Tests passing with small datasets but users reporting "ambiguous" errors in production.

### Pitfall 2: NULL Metric Values in Delta Calculations

**What goes wrong:** `delta_abs` and `delta_pct` calculations fail or produce misleading results when one or both metrics are NULL (e.g., failed scenarios have `score=inf`, `train_loss=None`).
**Why it happens:** Failed scenarios have NULL metrics. Computing `a - b` or `(a - b) / b` when either is None or inf raises TypeError or produces inf/nan.
**How to avoid:** Wrap all delta calculations in a null-safe helper that returns `None` (displayed as "--") when either operand is None or non-finite. Display status mismatch flags prominently when one side is failed/pending.
**Warning signs:** Unhandled `TypeError` or `ZeroDivisionError` in comparison output.

### Pitfall 3: Correlation as List vs Float in Alignment Key

**What goes wrong:** Two scenarios with the same correlation matrix are treated as different because Python `list` is unhashable or `list != list` for different object instances.
**Why it happens:** `scenario_json` stores correlation as either a float (scalar) or a nested list (matrix). `Scenario.as_parameters()` preserves the original type. Using raw parsed JSON as a dict key fails because lists are unhashable.
**How to avoid:** Normalize correlation to a JSON string for hashing (as shown in the alignment key pattern above). `json.dumps(corr, sort_keys=True)` produces a stable string representation.
**Warning signs:** Scenarios that should align showing up as "missing" in both sides.

### Pitfall 4: config_json vs manifest_hash for Filtering

**What goes wrong:** User expects `--manifest-hash` to filter by the experiment manifest content hash, but the `batch_runs` table stores `config_json` (batch config payload) not the manifest hash.
**Why it happens:** The manifest hash (`experiment_manifest_hash`) is computed from the full `ExperimentManifest` and passed to `run_batch_async`, but it is stored in the YAML manifest file on disk, not in the `batch_runs` SQLite table. The `config_json` column stores only the `BatchConfig` payload.
**How to avoid:** Phase 5 needs a schema migration (v2 -> v3) to add a `manifest_hash` column to `batch_runs`, OR read the manifest hash from the artifact YAML file. The migration approach is cleaner since SQL filtering is faster than loading YAML files. Alternatively, populate the field from the `RunManifest.experiment_manifest_hash` during `create_batch_run` -- but that requires modifying existing `create_batch_run` signature (breaking change). **Recommended:** Add a `manifest_hash TEXT` column via migration v2->v3, backfill from existing artifact files if present, and populate it going forward in the orchestrator.
**Warning signs:** `--manifest-hash` filter returns no results even when matching runs exist.

### Pitfall 5: Rich Table Output Width on Narrow Terminals

**What goes wrong:** Tables with many columns wrap awkwardly or truncate data on terminals narrower than ~100 characters.
**Why it happens:** `compare-runs` has many columns per metric (run_a, run_b, delta_abs, delta_pct x 4 metrics = 16 data columns plus scenario key).
**How to avoid:** Use `no_wrap=True` for identifier columns, `overflow="ellipsis"` for long values, and consider a compact mode (`--verbose` off) that shows fewer metrics. Rich `Table` with `expand=True` adapts to terminal width automatically.
**Warning signs:** Garbled output in CI/CD logs or when terminal is resized.

### Pitfall 6: best_score and median_score Aggregation for list-runs

**What goes wrong:** Computing best_score/median_score across all scenarios requires joining batch_runs with scenario_runs and aggregating, but the current MetadataStore has no aggregate query methods.
**Why it happens:** The `batch_runs` table stores `completed_count` and `failed_count` but not score aggregates. Score is stored per scenario_run row.
**How to avoid:** Use SQL aggregation: `SELECT batch_run_id, MIN(score), ... FROM scenario_runs WHERE status='completed' GROUP BY batch_run_id`. This is efficient and avoids loading all scenario rows into Python.
**Warning signs:** Slow list-runs when there are many scenarios per run.

## Code Examples

### MetadataStore New Query Methods

```python
# Source: Derived from existing metadata.py patterns

def list_batch_runs(
    self,
    status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    git_sha: str | None = None,
    manifest_hash: str | None = None,
    order_by: str = "created_at DESC",
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List batch runs with optional filters and pagination."""
    conditions: list[str] = []
    params: list[Any] = []

    if status is not None:
        conditions.append("b.status = ?")
        params.append(status)
    if from_date is not None:
        conditions.append("b.created_at >= ?")
        params.append(from_date)
    if to_date is not None:
        conditions.append("b.created_at <= ?")
        params.append(to_date)
    if git_sha is not None:
        conditions.append("b.git_sha = ?")
        params.append(git_sha)
    if manifest_hash is not None:
        conditions.append("b.manifest_hash = ?")
        params.append(manifest_hash)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    # Allowlist for order_by to prevent SQL injection
    allowed_orders = {"created_at DESC", "created_at ASC"}
    if order_by not in allowed_orders:
        order_by = "created_at DESC"

    query = f"""
        SELECT b.*,
               MIN(CASE WHEN s.status = 'completed' THEN s.score END) AS best_score,
               COUNT(CASE WHEN s.status = 'completed' THEN 1 END) AS agg_completed_count,
               COUNT(CASE WHEN s.status = 'failed' THEN 1 END) AS agg_failed_count
        FROM batch_runs b
        LEFT JOIN scenario_runs s ON b.batch_run_id = s.batch_run_id
        WHERE {where_clause}
        GROUP BY b.batch_run_id
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    rows = self.connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def find_batch_runs_by_prefix(self, prefix: str) -> list[dict[str, Any]]:
    """Find batch runs whose batch_run_id starts with the given prefix."""
    rows = self.connection.execute(
        "SELECT * FROM batch_runs WHERE batch_run_id LIKE ? || '%'",
        (prefix,),
    ).fetchall()
    return [dict(row) for row in rows]
```

### Score Filter Integration (min_score, max_score)

```python
# min_score and max_score require joining with scenario_runs aggregates
# Applied as HAVING clause on the aggregate query

if min_score is not None:
    having_conditions.append("MIN(CASE WHEN s.status = 'completed' THEN s.score END) >= ?")
    having_params.append(min_score)
if max_score is not None:
    having_conditions.append("MIN(CASE WHEN s.status = 'completed' THEN s.score END) <= ?")
    having_params.append(max_score)
```

### Median Score Calculation

```python
# SQLite does not have a built-in MEDIAN() aggregate.
# Compute in Python after fetching completed scores for the batch.
from statistics import median

def _compute_median_score(scenario_rows: list[dict[str, Any]]) -> float | None:
    scores = [
        row["score"]
        for row in scenario_rows
        if row["status"] == "completed" and row["score"] is not None
    ]
    return median(scores) if scores else None
```

### Null-Safe Delta Helpers

```python
import math

def delta_abs(a: float | None, b: float | None) -> float | None:
    """Compute absolute delta, returning None if either is None or non-finite."""
    if a is None or b is None:
        return None
    try:
        a_f, b_f = float(a), float(b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(a_f) or not math.isfinite(b_f):
        return None
    return a_f - b_f

def delta_pct(a: float | None, b: float | None) -> float | None:
    """Compute percentage change from b to a: (a - b) / |b| * 100."""
    d = delta_abs(a, b)
    if d is None or b is None:
        return None
    b_f = float(b)
    if b_f == 0.0:
        return None
    return (d / abs(b_f)) * 100.0
```

### Rich Table for list-runs

```python
# Source: Existing leaderboard.py pattern
from rich.console import Console
from rich.table import Table

def render_runs_table(
    runs: list[dict[str, Any]],
    verbose: bool = False,
    console: Console | None = None,
) -> None:
    if console is None:
        console = Console(stderr=True)

    table = Table(title="Batch Runs", caption=f"{len(runs)} runs")
    table.add_column("Run ID", style="cyan", no_wrap=True, width=12)
    table.add_column("Created", style="dim", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Scenarios", justify="right")
    table.add_column("Done/Fail", justify="right")
    table.add_column("Best Score", justify="right", style="green")
    table.add_column("Median Score", justify="right")

    for run in runs:
        run_id_display = run["batch_run_id"][:12]
        # ... populate row
        table.add_row(...)

    console.print(table)
```

### Rich Panel + Table Mixed Layout for show-run

```python
# Source: Rich docs Panel + Table
from rich.panel import Panel
from rich.table import Table
from rich.console import Group

def render_show_run(batch_run: dict, scenarios: list[dict], console: Console) -> None:
    # Header panel with run metadata
    header_text = (
        f"Run ID: {batch_run['batch_run_id']}\n"
        f"Created: {batch_run['created_at']}\n"
        f"Status: {batch_run['status']}\n"
        f"Git SHA: {batch_run.get('git_sha', '--')}\n"
        f"Scenarios: {batch_run['scenario_count']}"
    )
    console.print(Panel(header_text, title="Run Details", border_style="blue"))

    # Scenario table
    table = Table(title="Scenarios")
    table.add_column("Scenario", style="cyan")
    table.add_column("Status")
    table.add_column("Score", justify="right")
    table.add_column("Health")
    table.add_column("Train Loss", justify="right")
    table.add_column("Grad Norm", justify="right")
    table.add_column("Progress", justify="right")
    # ... add rows
    console.print(table)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `sys.stdout.isatty()` for TTY detection | `Console().is_terminal` (Rich) | Rich 10+ (2021) | Handles edge cases (Jupyter, IDLE, Windows conhost). Already in codebase. |
| Manual column alignment with `str.ljust()` | `Rich.Table` with auto-sizing | Rich 10+ (2021) | Handles Unicode width, terminal resize, color codes in length calculation. |
| Typer 0.x with `click.testing.CliRunner` | Typer 0.21+ with `typer.testing.CliRunner` | Typer 0.9+ (2023) | Native Typer test runner. Already used in `test_cli.py`. |

**Deprecated/outdated:**
- `click.testing.CliRunner`: Typer provides its own `CliRunner` that wraps Click's. Use `typer.testing.CliRunner` (already the pattern in tests).
- `tabulate` / `prettytable`: Rich Table is more capable and already a dependency. No reason to add another table library.

## Open Questions

1. **manifest_hash column in batch_runs**
   - What we know: The `experiment_manifest_hash` is computed and passed through the orchestrator but is NOT stored in the `batch_runs` SQLite table. It IS written to the YAML manifest file in the artifacts directory.
   - What's unclear: Whether to add a schema migration (v2->v3) to add a `manifest_hash` column, or read from the artifact YAML at query time.
   - Recommendation: Add migration v2->v3 with `manifest_hash TEXT` column. Populate in `create_batch_run` going forward. For existing runs, the column will be NULL (acceptable -- old runs simply won't match `--manifest-hash` filter). This is cleaner than reading YAML files during list queries.

2. **median_score computation strategy**
   - What we know: SQLite lacks a built-in `MEDIAN()` aggregate. The `list_batch_runs` query uses SQL aggregation for `best_score` (MIN) and counts.
   - What's unclear: Whether to compute median in a second query, a subquery, or in Python after the initial fetch.
   - Recommendation: For the initial `list_batch_runs`, only compute `best_score` in SQL (via MIN). Compute `median_score` in Python using `statistics.median()` on the scores fetched in a secondary query per batch, OR fetch all completed scores in a single batch-aware query and compute in Python. The median is only needed for display, not filtering, so Python-side computation is acceptable.

3. **show-run convergence_health from result_json or recompute**
   - What we know: `convergence_health` is stored in `result_json` for each scenario as a string. It could also be recomputed from the stored metrics.
   - What's unclear: Whether to just display the stored value or recompute.
   - Recommendation: Display the stored value from `result_json`. Recomputation would be inconsistent if diagnostics heuristics change between versions. Show what was computed at run time.

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** -- All source files in `src/fk_quant_research_accel/` read directly
  - `store/metadata.py` -- MetadataStore API (17 lines of query methods, 223 total)
  - `store/migrations.py` -- Schema definition (batch_runs, scenario_runs tables)
  - `cli.py` -- Existing Typer CLI patterns (run-batch, resume-batch)
  - `leaderboard.py` -- Rich Table rendering pattern
  - `orchestrator.py` -- Scenario generation and `scenario_json` structure
  - `async_orchestrator.py` -- How scenario_json is stored and parsed for resume
  - `models/result.py` -- ScenarioResult schema with all available metrics
  - `models/ids.py` -- BatchRunId NewType and UUID generation
  - `tests/test_cli.py` -- CliRunner test patterns
  - `tests/test_leaderboard.py` -- Rich Console test patterns (StringIO buffer)
  - `tests/test_store.py` -- MetadataStore test patterns (tmp_path)

### Secondary (MEDIUM confidence)
- **Rich docs (Context7)** `/websites/rich_readthedocs_io_en_stable` -- Console.is_terminal, Table API, Panel, force_terminal
- **Typer docs (Context7)** `/websites/typer_tiangolo` -- @app.command, Argument, Option, CliRunner, add_typer subcommands

### Tertiary (LOW confidence)
- None. All findings verified against codebase or official docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already installed and used in codebase
- Architecture: HIGH -- patterns directly derived from existing codebase (leaderboard.py, cli.py, metadata.py)
- Pitfalls: HIGH -- identified from direct code analysis (e.g., manifest_hash gap verified by reading migration schema and orchestrator code)

**Research date:** 2026-02-23
**Valid until:** 2026-03-23 (stable domain, no fast-moving external dependencies)
