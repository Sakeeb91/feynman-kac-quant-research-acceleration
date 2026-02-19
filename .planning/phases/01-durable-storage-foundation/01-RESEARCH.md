# Phase 1: Durable Storage Foundation - Research

**Researched:** 2026-02-19
**Domain:** Crash-safe experiment storage, structured logging, reproducibility metadata, SQLite persistence, artifact directory layout
**Confidence:** HIGH

## Summary

Phase 1 transforms the existing fragile prototype into a crash-safe, observable experiment platform. The current codebase holds all state in Python lists (`submitted`, `records` in `orchestrator.py:68-69`), writes a single CSV to a flat path (`artifacts/batch_results.csv`), uses `print()` for output (3 call sites in `cli.py`), and loses everything on process termination. Phase 1 fixes every one of these problems by layering in: (1) a SQLite metadata store with WAL mode for ACID-compliant crash recovery, (2) a structured artifact directory tree (`artifacts/{batch_run_id}/{scenario_run_id}/`), (3) structlog-based structured logging with CLI-configurable `--log-level`, (4) a manifest file capturing full config + reproducibility metadata per run, (5) incremental per-scenario writes so completed results survive crashes, and (6) durable storage of training checkpoints fetched from the FK backend.

The technical domain is well-established. SQLite WAL mode for crash-safe writes is a proven pattern (used by MLflow, Firefox, every iOS app). Structlog's `make_filtering_bound_logger()` provides efficient log-level filtering with bound context variables (run_id, scenario params). Pydantic v2 frozen models replace frozen dataclasses for manifest serialization with validation. The `PRAGMA user_version` pattern provides lightweight schema migration without external dependencies.

**Primary recommendation:** Use stdlib SQLite with WAL mode and `PRAGMA user_version` for schema versioning. Use structlog with `make_filtering_bound_logger()` for level-configurable structured logging. Use Pydantic v2 frozen BaseModel for manifest/result schemas. Use `subprocess.run(["git", "rev-parse", "HEAD"])` for git SHA capture (avoid gitpython dependency). Write each scenario result to disk immediately after completion, both to SQLite and to the artifact directory.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| SQLite (stdlib `sqlite3`) | Python stdlib | Experiment metadata store, run state tracking, crash recovery | Zero-dependency, ACID-compliant with WAL mode, proven by MLflow local tracking. Single-writer constraint is fine for solo researcher. Survives process crashes by design. | HIGH |
| Pydantic | >=2.12.5 | Manifest schemas, result models, config validation | Replaces frozen dataclasses (`Scenario`, `BatchConfig`) with validated, serializable models. `BaseModel(frozen=True)` preserves immutability. `model_dump(mode="json")` produces YAML/JSON-serializable dicts. `model_json_schema()` generates JSON Schema for manifest versioning. | HIGH |
| structlog | >=25.5.0 | Structured logging with configurable levels | `make_filtering_bound_logger(logging.INFO)` provides fast upfront filtering. Bound loggers carry context (batch_run_id, scenario_run_id) across all log calls. JSON output makes logs queryable. Replaces 3 `print()` call sites in cli.py. | HIGH |
| PyYAML | >=6.0.3 | Manifest file serialization/deserialization | `yaml.safe_dump()` for writing manifest.yaml, `yaml.safe_load()` for reading. Human-readable, diffable, git-versionable. Standard for ML config files. | HIGH |

### Supporting

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| Typer | >=0.21.0 | CLI framework with `--log-level` flag | Replaces argparse. `@app.callback()` provides global `--log-level` option. Enum parameter for log level selection. | HIGH |
| Rich | >=14.2.0 | Terminal output formatting | Leaderboard display, progress indicators. Integrates with Typer. | MEDIUM |
| subprocess (stdlib) | Python stdlib | Git SHA + dirty status capture | `subprocess.run(["git", "rev-parse", "HEAD"])` at experiment creation time. Captures dirty status with `subprocess.run(["git", "status", "--porcelain"])`. | HIGH |
| importlib.metadata (stdlib) | Python stdlib | Package version capture for reproducibility | `importlib.metadata.distributions()` to capture installed package versions without subprocess. Replaces `pip freeze` for programmatic access. | MEDIUM |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| subprocess for git SHA | gitpython >=3.1.44 | gitpython adds a dependency and has known performance overhead (extra `git rev-parse` calls per operation). For our use case (read HEAD SHA + dirty status once per batch), subprocess is simpler, faster, and zero-dependency. |
| `PRAGMA user_version` | yoyo-migrations or caribou | External migration libraries add dependencies and complexity. With <10 tables and infrequent schema changes, `PRAGMA user_version` + inline migration functions is sufficient. |
| structlog | loguru | Loguru is simpler to configure but lacks structured key-value output. For a research platform where logs carry experiment metadata (run_id, scenario params), structlog's bound logger pattern is a better fit. |
| structlog | stdlib logging | stdlib logging requires more boilerplate for structured output. structlog wraps stdlib logging with a cleaner API and better context binding. |
| Pydantic BaseModel | frozen dataclasses (existing) | Frozen dataclasses work but lack validation, JSON Schema generation, and `model_dump()` serialization. Pydantic adds these for free with minimal migration effort. |
| PyYAML safe_dump | TOML (tomllib) | TOML is in stdlib since 3.11 (read-only) but requires `tomli-w` for writing. YAML is the standard for ML experiment configs. No benefit to switching. |

**Installation:**

```bash
pip install "pydantic>=2.12.5" "structlog>=25.5.0" "PyYAML>=6.0.3" "typer>=0.21.0" "rich>=14.2.0"
```

## Architecture Patterns

### Recommended Project Structure (Phase 1 additions)

```
src/fk_quant_research_accel/
├── __init__.py               # Public API exports (existing, extended)
├── cli.py                    # CLI entry point (existing, migrated to Typer)
├── client.py                 # FK PINN HTTP client (existing, preserved as-is)
├── orchestrator.py           # Batch orchestration (existing, modified for incremental writes)
├── reporting.py              # Scoring and CSV export (existing, preserved)
├── logging.py                # structlog configuration and setup
├── models/                   # Domain models (Pydantic v2)
│   ├── __init__.py
│   ├── ids.py                # BatchRunId, ScenarioRunId type definitions
│   ├── manifest.py           # RunManifest model (full config + repro metadata)
│   ├── result.py             # ScenarioResult model (per-scenario output)
│   └── enums.py              # ScenarioStatus, LogLevel enums
└── store/                    # Storage layer
    ├── __init__.py
    ├── metadata.py           # SQLite metadata store (experiments, scenarios)
    ├── artifacts.py          # Filesystem artifact store (directory management)
    └── migrations.py         # PRAGMA user_version based schema versioning
```

### Pattern 1: Incremental Write-Through on Scenario Completion

**What:** Each scenario result is written to both SQLite and the artifact directory the moment it completes, not accumulated in memory and written at the end. This is the crash-safety guarantee.

**When to use:** Every scenario completion, whether success or failure.

**Example:**

```python
# Source: Architecture pattern from MLflow local tracking + research analysis
import sqlite3
import json
from pathlib import Path

def persist_scenario_result(
    db_conn: sqlite3.Connection,
    artifact_dir: Path,
    batch_run_id: str,
    scenario_run_id: str,
    result: dict,
    status: str,
    error_message: str | None = None,
) -> None:
    """Write scenario result to both SQLite and filesystem atomically."""
    # 1. Write to SQLite (ACID-compliant with WAL)
    db_conn.execute(
        """INSERT OR REPLACE INTO scenario_runs
           (scenario_run_id, batch_run_id, status, result_json, error_message, completed_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (scenario_run_id, batch_run_id, status, json.dumps(result), error_message),
    )
    db_conn.commit()  # Explicit commit per scenario -- crash-safe

    # 2. Write to artifact directory
    scenario_dir = artifact_dir / batch_run_id / scenario_run_id
    scenario_dir.mkdir(parents=True, exist_ok=True)

    result_file = scenario_dir / "result.json"
    # Atomic write: write to temp file, then rename
    tmp = result_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.rename(result_file)
```

### Pattern 2: SQLite with WAL Mode and PRAGMA user_version

**What:** Enable WAL (Write-Ahead Logging) mode for concurrent read access and crash safety. Use `PRAGMA user_version` as a lightweight schema version tracker. Apply migrations incrementally at startup.

**When to use:** Database initialization at application startup.

**Example:**

```python
# Source: SQLite WAL docs (https://sqlite.org/wal.html),
#         PRAGMA user_version pattern (https://eskerda.com/sqlite-schema-migrations-python/)
import sqlite3

CURRENT_SCHEMA_VERSION = 1

def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize SQLite database with WAL mode and schema migrations."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # Wait 5s on lock contention
    conn.row_factory = sqlite3.Row  # Dict-like row access

    version = conn.execute("PRAGMA user_version").fetchone()[0]
    _apply_migrations(conn, version)
    return conn

def _apply_migrations(conn: sqlite3.Connection, current_version: int) -> None:
    """Apply schema migrations from current_version to CURRENT_SCHEMA_VERSION."""
    migrations = {
        0: _migrate_v0_to_v1,
        # Future: 1: _migrate_v1_to_v2, ...
    }
    for v in range(current_version, CURRENT_SCHEMA_VERSION):
        migrations[v](conn)
        conn.execute(f"PRAGMA user_version = {v + 1}")
        conn.commit()

def _migrate_v0_to_v1(conn: sqlite3.Connection) -> None:
    """Initial schema creation."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS batch_runs (
            batch_run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            config_json TEXT NOT NULL,
            manifest_schema_version INTEGER NOT NULL DEFAULT 1,
            git_sha TEXT,
            git_dirty INTEGER,
            python_version TEXT,
            os_info TEXT,
            seed INTEGER,
            scenario_count INTEGER NOT NULL,
            completed_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            artifact_path TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scenario_runs (
            scenario_run_id TEXT PRIMARY KEY,
            batch_run_id TEXT NOT NULL REFERENCES batch_runs(batch_run_id),
            scenario_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            simulation_id TEXT,
            result_json TEXT,
            score REAL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            checkpoint_path TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_scenario_batch
            ON scenario_runs(batch_run_id);
        CREATE INDEX IF NOT EXISTS idx_scenario_status
            ON scenario_runs(status);
    """)
```

### Pattern 3: structlog Configuration with CLI-Driven Log Level

**What:** Configure structlog at application startup based on the `--log-level` CLI flag. Use `make_filtering_bound_logger()` for fast upfront filtering. Bind batch_run_id and scenario context to loggers.

**When to use:** Application startup, before any other module is imported.

**Example:**

```python
# Source: structlog docs (https://www.structlog.org/en/stable/configuration.html),
#         Context7 /hynek/structlog
import logging
import sys
import structlog

def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with the given log level."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

# Usage in orchestrator:
log = structlog.get_logger()
log = log.bind(batch_run_id=batch_run_id)

log.info("batch_started", scenario_count=len(scenarios))

# Per-scenario logging with bound context:
scenario_log = log.bind(scenario_run_id=scenario_run_id, dim=scenario.dim)
scenario_log.info("scenario_submitted", simulation_id=sim_id)
scenario_log.info("scenario_completed", score=0.0234, train_loss=0.021)
scenario_log.error("scenario_failed", error="TimeoutError: ...")
```

### Pattern 4: Typer Callback for Global --log-level Option

**What:** Use Typer's `@app.callback()` to define a global `--log-level` option that applies to all subcommands. Use a `str` Enum for the log level choices.

**When to use:** CLI entry point.

**Example:**

```python
# Source: Context7 /fastapi/typer -- callback and enum parameter docs
from enum import Enum
from typing import Optional
import typer

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

app = typer.Typer(
    name="fk-research",
    help="FK Quant Research Acceleration Platform",
)

@app.callback()
def main(
    log_level: LogLevel = typer.Option(
        LogLevel.INFO, "--log-level", help="Set logging verbosity"
    ),
) -> None:
    """Configure global options."""
    from .logging import configure_logging
    configure_logging(log_level.value)

@app.command()
def run_batch(
    base_url: str = typer.Option(..., help="FK PINN backend base URL"),
    # ... other options
) -> None:
    """Submit a Black-Scholes scenario grid."""
    ...
```

### Pattern 5: Manifest Serialization with Pydantic + PyYAML

**What:** Serialize the full run config (scenario grid, batch config, git SHA, seed, schema versions) as a `manifest.yaml` file using Pydantic's `model_dump(mode="json")` piped through `yaml.safe_dump()`.

**When to use:** At batch creation time, before any scenario is submitted.

**Example:**

```python
# Source: Pydantic v2 docs (Context7 /websites/pydantic_dev_2_12),
#         PyYAML safe_dump
import yaml
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import UUID

class ManifestMetadata(BaseModel, frozen=True):
    manifest_schema_version: int = 1
    result_schema_version: int = 1
    db_migration_version: int = 1

class ReproducibilityInfo(BaseModel, frozen=True):
    git_sha: str | None = None
    git_dirty: bool | None = None
    python_version: str
    os_info: str
    seed: int | None = None
    packages: dict[str, str] = Field(default_factory=dict)

class RunManifest(BaseModel, frozen=True):
    batch_run_id: str
    created_at: datetime
    schema_versions: ManifestMetadata = Field(default_factory=ManifestMetadata)
    reproducibility: ReproducibilityInfo
    batch_config: dict  # BatchConfig.model_dump()
    scenarios: list[dict]  # [Scenario.model_dump() for each]
    backend_url: str

def write_manifest(manifest: RunManifest, artifact_dir: Path) -> Path:
    """Write manifest.yaml to the batch artifact directory."""
    manifest_path = artifact_dir / manifest.batch_run_id / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    data = manifest.model_dump(mode="json")
    # Atomic write
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False), encoding="utf-8")
    tmp.rename(manifest_path)
    return manifest_path
```

### Pattern 6: Reproducibility Metadata Capture

**What:** Automatically capture git SHA, dirty status, Python version, OS info, and installed package versions at batch creation time. Use stdlib only (subprocess, sys, platform, importlib.metadata).

**When to use:** Every batch run creation, before scenarios are submitted.

**Example:**

```python
# Source: Python stdlib docs, git rev-parse pattern
#         (https://gist.github.com/ethanwhite/ba63849c26301f862e4e)
import subprocess
import sys
import platform
import importlib.metadata

def capture_git_info(repo_path: str = ".") -> tuple[str | None, bool | None]:
    """Capture git HEAD SHA and dirty status. Returns (sha, dirty) or (None, None) if not a git repo."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=repo_path,
        ).stdout.strip() or None
        dirty_output = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, cwd=repo_path,
        ).stdout.strip()
        dirty = bool(dirty_output) if sha else None
        return sha, dirty
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, None

def capture_environment() -> dict:
    """Capture reproducibility metadata."""
    packages = {
        dist.metadata["Name"]: dist.metadata["Version"]
        for dist in importlib.metadata.distributions()
        if dist.metadata["Name"]  # Filter out None names
    }
    return {
        "python_version": sys.version,
        "os_info": platform.platform(),
        "packages": packages,
    }
```

### Pattern 7: Checkpoint Persistence from FK Backend

**What:** After a scenario completes successfully, fetch the training checkpoint from the FK PINN backend and store it in the scenario's artifact directory. This enables downstream model packaging (Phase 7 prerequisite).

**When to use:** After each successful scenario completion, before marking it as fully persisted.

**Design considerations:**
- The FK backend checkpoint API is not yet fully documented (see Open Questions)
- Design the checkpoint fetch as an optional step that does not block scenario completion
- Store checkpoint path in the scenario_runs SQLite record for later retrieval
- Use atomic write pattern (write to temp, rename) for large checkpoint files

**Example (interface-level -- implementation depends on backend API):**

```python
def fetch_and_store_checkpoint(
    client: FKPinnClient,
    simulation_id: str,
    scenario_dir: Path,
) -> Path | None:
    """Fetch checkpoint from FK backend and store in scenario artifact directory.

    Returns path to stored checkpoint, or None if checkpoint unavailable.
    """
    checkpoint_dir = scenario_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    try:
        # API shape TBD -- this is the interface we need from the backend
        # Option A: GET /api/v1/simulations/{id}/checkpoint (returns binary)
        # Option B: GET /api/v1/results/{id} includes checkpoint_url field
        checkpoint_data = client.get_checkpoint(simulation_id)
        if checkpoint_data is None:
            return None

        checkpoint_path = checkpoint_dir / "model_checkpoint.pt"
        tmp = checkpoint_path.with_suffix(".tmp")
        tmp.write_bytes(checkpoint_data)
        tmp.rename(checkpoint_path)
        return checkpoint_path

    except Exception:
        # Checkpoint fetch failure should not fail the scenario
        structlog.get_logger().warning(
            "checkpoint_fetch_failed",
            simulation_id=simulation_id,
            exc_info=True,
        )
        return None
```

### Anti-Patterns to Avoid

- **Batch-at-end writes:** Never accumulate all results in memory and write at the end. This is the current pattern (`orchestrator.py:68-105`) and is the primary cause of data loss.
- **Single-file output:** Never write all results to a single flat file (`artifacts/batch_results.csv`). Use `artifacts/{batch_run_id}/{scenario_run_id}/` directory tree.
- **print() for logging:** Never use `print()` for platform output. Every print statement becomes invisible in production and cannot be filtered or queried.
- **Implicit schema versions:** Never create a schema without a version number. Every table schema, manifest format, and result format must have an explicit version from day one.
- **In-memory-only experiment state:** Never track experiments solely in Python data structures. All state transitions must be persisted to SQLite.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured logging | Custom logging with `print()` + timestamp formatting | structlog `make_filtering_bound_logger()` | Bound context, JSON output, level filtering, stdlib integration -- hundreds of edge cases in logging (thread safety, exception formatting, encoding) |
| Schema migration | Custom migration tracking with a `migrations` table + file scanner | `PRAGMA user_version` + inline migration functions | SQLite provides the version tracking for free. Inline functions avoid file management. Sufficient for <10 tables. |
| YAML serialization | Custom dict-to-YAML converter | PyYAML `safe_dump()` + Pydantic `model_dump(mode="json")` | YAML formatting edge cases (multiline strings, unicode, None vs null, empty collections) are handled by PyYAML |
| UUID generation | Custom ID generation | `uuid.uuid4()` (stdlib) | UUIDs are universally unique, collision-free, and sort correctly in SQLite text columns |
| Atomic file writes | Direct `file.write()` | Write-to-temp + `os.rename()` pattern | `os.rename()` is atomic on POSIX systems. Direct writes can leave corrupted files on crash. |
| Config validation | Custom validation functions | Pydantic `BaseModel` with type annotations and validators | Pydantic's Rust core validates faster than Python, generates JSON Schema, provides clear error messages |
| CLI framework | argparse (existing) | Typer with `@app.callback()` for global options | Type-hint-driven, auto-generated help, enum support for `--log-level`, less boilerplate than argparse |
| Environment capture | Multiple subprocess calls to pip, python, etc. | `sys.version` + `platform.platform()` + `importlib.metadata.distributions()` | All in stdlib, no subprocess overhead, works in restricted environments |

**Key insight:** Phase 1 introduces only one new non-stdlib dependency for the storage layer (structlog). SQLite, subprocess, importlib.metadata, uuid, json, and pathlib are all stdlib. Pydantic and PyYAML are used for serialization but add no operational complexity. This keeps the complexity budget tight.

## Common Pitfalls

### Pitfall 1: SQLite Connection Sharing Across Threads

**What goes wrong:** Python's `sqlite3` module has thread-safety restrictions. Passing a connection across threads produces `ProgrammingError: SQLite objects created in a thread can only be used in that same thread` (default behavior) or silent corruption if `check_same_thread=False` is used carelessly.

**Why it happens:** Phase 1 is single-threaded (concurrent execution is Phase 3), but developers may pre-emptively add threading without updating the database layer.

**How to avoid:** Keep `check_same_thread=True` (default). Create a new connection per function call if needed, or use a connection pool. WAL mode allows concurrent readers with a single writer. For Phase 1 (sequential execution), a single connection per batch run is sufficient.

**Warning signs:** `ProgrammingError` exceptions, or silently corrupted database rows.

### Pitfall 2: Forgetting to Commit After Each Scenario

**What goes wrong:** SQLite auto-commit is disabled when you call `conn.execute()` within an implicit transaction. If you write 15 scenario results without explicit `conn.commit()` calls and the process crashes, all 15 are lost -- defeating the entire purpose of incremental writes.

**Why it happens:** Developers assume `conn.execute("INSERT ...")` is durable. It is not until `conn.commit()` is called (or the connection is closed cleanly, which does not happen on crash).

**How to avoid:** Call `conn.commit()` after every scenario result write. This is the price of crash safety. The performance cost (~1ms per commit with WAL mode) is negligible compared to 30-minute PINN training runs.

**Warning signs:** Missing scenario results after a crash, even though the code wrote them.

### Pitfall 3: YAML Manifest Non-Determinism

**What goes wrong:** `yaml.safe_dump()` can produce different output for the same Python dict depending on key insertion order (Python 3.7+ dicts are ordered by insertion, but YAML spec does not guarantee key ordering). If manifest hashing is added later (Phase 2, CONF-03), non-deterministic YAML output means identical configs produce different hashes.

**Why it happens:** YAML is a superset of JSON, and YAML formatting choices (flow style, block style, key order) are implementation-dependent.

**How to avoid:** For Phase 1, use `yaml.safe_dump(data, default_flow_style=False, sort_keys=True)` with `sort_keys=True` to produce deterministic output. When manifest hashing is added in Phase 2, hash the JSON-normalized form (`json.dumps(data, sort_keys=True, separators=(",", ":"))`) rather than the YAML text.

**Warning signs:** Same config producing different manifest files on different runs.

### Pitfall 4: Artifact Directory Collisions from Truncated UUIDs

**What goes wrong:** Using truncated UUIDs (e.g., first 8 chars) for directory names to make them "readable" introduces collision risk. At 100 batches, 8-hex-char collision probability is ~0.01%. At 10,000 batches, it is ~1%.

**Why it happens:** Full UUIDs (`550e8400-e29b-41d4-a716-446655440000`) look ugly in directory listings. Developers truncate for aesthetics.

**How to avoid:** Use full UUIDs for `batch_run_id` and `scenario_run_id`. They are ugly but guaranteed unique. If readability matters, add a human-readable prefix: `20260219T143022_550e8400` (timestamp + UUID). Never truncate the UUID portion.

**Warning signs:** Directory already exists errors during batch creation.

### Pitfall 5: Schema Version Mismatch After Partial Migration

**What goes wrong:** If a migration crashes halfway (e.g., `CREATE TABLE` succeeds but `CREATE INDEX` fails), the `PRAGMA user_version` is not updated, but the database is in a partially migrated state. Re-running the migration fails because the table already exists.

**Why it happens:** `PRAGMA user_version` is set after the migration function completes. If the function crashes, the version stays at the old value.

**How to avoid:** Use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` in all migration DDL. This makes migrations idempotent -- they can be re-run safely. Also wrap each migration in a transaction (SQLite DDL is transactional).

**Warning signs:** `OperationalError: table already exists` on startup.

### Pitfall 6: Checkpoint Fetch Blocking Scenario Completion

**What goes wrong:** If checkpoint fetching from the FK backend is slow, times out, or the endpoint does not exist yet, it blocks the entire batch run. A 404 from the checkpoint endpoint should not fail a scenario that otherwise completed successfully.

**Why it happens:** Developers treat checkpoint persistence as a mandatory step in the scenario completion pipeline rather than an optional enrichment step.

**How to avoid:** Fetch checkpoints in a try/except block. Log warnings on failure. Store `checkpoint_path = NULL` in the database for scenarios without checkpoints. Phase 7 (model packaging) checks for checkpoint availability and reports which scenarios have checkpoints.

**Warning signs:** Batch runs failing due to checkpoint-related errors even though training completed successfully.

## Code Examples

Verified patterns from official sources:

### SQLite WAL Mode Initialization

```python
# Source: https://sqlite.org/wal.html, https://charlesleifer.com/blog/going-fast-with-sqlite-and-python/
import sqlite3

conn = sqlite3.connect("experiments.db")
conn.execute("PRAGMA journal_mode=WAL")       # Enable WAL mode
conn.execute("PRAGMA synchronous=NORMAL")     # Safe with WAL; full sync only on checkpoint
conn.execute("PRAGMA foreign_keys=ON")        # Enforce FK constraints
conn.execute("PRAGMA busy_timeout=5000")      # Wait 5s on lock contention
conn.row_factory = sqlite3.Row               # Dict-like row access
```

### structlog with Configurable Level (Full Setup)

```python
# Source: Context7 /hynek/structlog -- make_filtering_bound_logger + contextvars
import logging
import sys
import structlog

def configure_logging(level_name: str = "INFO") -> None:
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

# Usage:
log = structlog.get_logger()
log = log.bind(batch_run_id="abc-123")
log.info("batch_started", scenario_count=16)
```

### Pydantic Frozen Model with YAML Serialization

```python
# Source: Context7 /websites/pydantic_dev_2_12 -- frozen BaseModel + model_dump
import yaml
from pydantic import BaseModel, Field

class Scenario(BaseModel, frozen=True):
    dim: int
    volatility: float
    correlation: float
    option_type: str = "call"

class BatchConfig(BaseModel, frozen=True):
    n_steps: int = 40
    batch_size: int = 64
    n_mc_paths: int = 256
    learning_rate: float = 1e-3

# Serialize to YAML:
scenario = Scenario(dim=5, volatility=0.2, correlation=0.3)
yaml_str = yaml.safe_dump(
    scenario.model_dump(mode="json"),
    default_flow_style=False,
    sort_keys=True,
)
# Output:
# correlation: 0.3
# dim: 5
# option_type: call
# volatility: 0.2

# Deserialize from YAML:
data = yaml.safe_load(yaml_str)
scenario_restored = Scenario.model_validate(data)
assert scenario == scenario_restored
```

### Typer CLI with --log-level Enum

```python
# Source: Context7 /fastapi/typer -- callback + enum parameter
from enum import Enum
import typer

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

app = typer.Typer(name="fk-research")

@app.callback()
def main_callback(
    log_level: LogLevel = typer.Option(LogLevel.INFO, "--log-level", help="Logging verbosity"),
) -> None:
    from .logging import configure_logging
    configure_logging(log_level.value)

@app.command("run-batch")
def run_batch_cmd(
    base_url: str = typer.Option(..., "--base-url", help="FK PINN backend URL"),
    dimensions: str = typer.Option("5,10", help="Comma-separated dimensions"),
    output: str = typer.Option("artifacts/batch_results.csv", help="Output path"),
) -> None:
    """Submit a Black-Scholes scenario grid."""
    ...
```

### Atomic File Write Pattern

```python
# Source: POSIX rename semantics, standard crash-safe write pattern
from pathlib import Path
import json

def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON file atomically using temp-file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.rename(path)  # Atomic on POSIX; overwrites existing

def atomic_write_text(path: Path, content: str) -> None:
    """Write text file atomically."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.rename(path)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@dataclass(frozen=True)` | `class Model(BaseModel, frozen=True)` | Pydantic v2 (June 2023) | Validation, serialization, JSON Schema all free with frozen=True |
| `requests` for HTTP | `httpx` for async HTTP | httpx 0.24+ (2023) | Phase 3 migration; for Phase 1 keep `requests` (sync client preserved) |
| `argparse` for CLI | Typer (type-hint-driven) | Typer 0.9+ (2023) | Less boilerplate, auto-completion, Rich integration |
| `print()` for output | structlog structured logging | structlog 21+ (2021) | JSON output, bound context, level filtering |
| `PRAGMA journal_mode=DELETE` | `PRAGMA journal_mode=WAL` | SQLite 3.7.0 (2010) | Concurrent readers, better crash recovery, faster writes |
| Custom migration scripts + files | `PRAGMA user_version` | Always available in SQLite | Zero-dependency schema versioning; sufficient for <10 tables |
| `gitpython` for repo inspection | `subprocess.run(["git", ...])` | Community shift (2023-2024) | Fewer dependencies, better performance for simple operations |

**Deprecated/outdated:**
- Pydantic v1 `Config` inner class: Use `model_config = ConfigDict(frozen=True)` or `class Model(BaseModel, frozen=True)` in v2
- `yaml.load()` without Loader: Always use `yaml.safe_load()` (security) or `yaml.load(data, Loader=yaml.SafeLoader)`
- Sacred for experiment tracking: Abandoned, no Python 3.12+ support
- `logging.basicConfig()` + structlog: Use structlog's own `PrintLoggerFactory` for cleaner setup

## Open Questions

1. **FK PINN Backend Checkpoint API**
   - What we know: The client has `get_result()` which returns metrics. Training checkpoints are stored somewhere in the backend.
   - What's unclear: Is there a dedicated endpoint for fetching checkpoints (e.g., `GET /api/v1/simulations/{id}/checkpoint`)? What format are checkpoints in (PyTorch `.pt`, ONNX, safetensors)? How large are typical checkpoints (KB? MB? GB?)? Does the checkpoint include optimizer state?
   - Recommendation: Design the `fetch_and_store_checkpoint()` interface now (Pattern 7 above). Implement the actual fetch when the backend API is documented. Store checkpoints as opaque binary blobs in `checkpoint/` subdirectory. Make checkpoint fetch optional and non-blocking.

2. **FK PINN Backend Metric Schema Stability**
   - What we know: The client already handles metric key instability (`metrics.get("loss", metrics.get("train_loss"))` in orchestrator.py:97). This means the backend has changed metric key names at least once.
   - What's unclear: Which metric keys are stable across backend versions? Does the backend return separate PDE residual, boundary loss, and IC loss, or only aggregate `train_loss`?
   - Recommendation: For Phase 1, store raw `result_json` as-is (preserve backend response verbatim). Extract known metrics (train_loss, val_loss, grad_norm, lr, progress) with fallback defaults. Do not build a strict result schema that rejects unknown keys -- store extra keys for future use. Strict schema validation is Phase 2.

3. **FK PINN Backend 404 Semantics**
   - What we know: The client calls `get_simulation()` during polling. If the backend restarts, previously submitted simulation IDs may disappear.
   - What's unclear: Does a 404 on `get_simulation()` mean "never existed" or "expired/garbage-collected"?
   - Recommendation: For Phase 1, treat 404 during polling as a scenario failure with error `"simulation_not_found"`. Log a warning. Do not retry (the simulation state is unknown). This is conservative but safe.

4. **Artifact Directory Root Location**
   - What we know: Current code writes to `artifacts/batch_results.csv` relative to CWD.
   - What's unclear: Should the artifact root be configurable? Relative to CWD or an absolute path? Should it be inside the git repo (and gitignored) or outside?
   - Recommendation: Default to `artifacts/` relative to CWD (matches current behavior). Add `--artifacts-dir` CLI option for override. Add `artifacts/` to `.gitignore`. The manifest records the absolute path for reproducibility.

5. **Database File Location**
   - What we know: No database exists yet.
   - What's unclear: Should the database be inside `artifacts/` (co-located with data) or separate (e.g., `.fk-research/experiments.db`)?
   - Recommendation: Store at `artifacts/experiments.db` (co-located). The database and artifact directories have the same lifecycle -- if you move artifacts, you move the database. Single location simplifies backup and cleanup.

## Sources

### Primary (HIGH confidence)

- [SQLite WAL Mode documentation](https://sqlite.org/wal.html) -- ACID crash safety guarantees, concurrent reader behavior, checkpoint semantics
- [Context7 /hynek/structlog](https://github.com/hynek/structlog) -- `make_filtering_bound_logger()`, `contextvars.merge_contextvars`, processor pipeline, JSON renderer
- [Context7 /websites/pydantic_dev_2_12](https://docs.pydantic.dev/2.12/) -- `BaseModel(frozen=True)`, `model_dump(mode="json")`, `model_json_schema()`, `model_validate()`
- [Context7 /fastapi/typer](https://github.com/fastapi/typer) -- `@app.callback()` for global options, Enum parameter types, subcommand patterns
- [structlog configuration docs](https://www.structlog.org/en/stable/configuration.html) -- `configure()` with `make_filtering_bound_logger()`, runtime level changes
- [structlog standard library integration](https://www.structlog.org/en/stable/standard-library.html) -- `filter_by_level`, `BoundLogger`, `LoggerFactory`
- [Pydantic v2 serialization docs](https://docs.pydantic.dev/latest/concepts/serialization/) -- `model_dump()`, `model_dump_json()`, mode parameter
- [SQLite PRAGMA user_version](https://sqlite.org/pragma.html#pragma_user_version) -- application-defined schema version tracking

### Secondary (MEDIUM confidence)

- [Going Fast with SQLite and Python (Charles Leifer)](https://charlesleifer.com/blog/going-fast-with-sqlite-and-python/) -- WAL mode performance, busy_timeout, synchronous=NORMAL tradeoffs
- [SQLite performance tuning (phiresky)](https://phiresky.github.io/blog/2020/sqlite-performance-tuning/) -- WAL mode configuration, concurrent access patterns
- [Suckless SQLite schema migrations in Python (eskerda)](https://eskerda.com/sqlite-schema-migrations-python/) -- PRAGMA user_version migration pattern implementation
- [SQLite DB Migrations with PRAGMA user_version (Lev Lazinskiy)](https://levlaz.org/sqlite-db-migrations-with-pragma-user_version/) -- Practical PRAGMA user_version examples
- [Pydantic YAML validation pattern (Sarah Glasmacher)](https://www.sarahglasmacher.com/how-to-validate-config-yaml-pydantic/) -- PyYAML safe_load + model_validate pattern
- [Git hash via Python built-ins (GitHub Gist)](https://gist.github.com/ethanwhite/ba63849c26301f862e4e) -- subprocess approach for git SHA
- [DVC GitPython migration discussion](https://github.com/iterative/dvc/issues/2215) -- DVC moved away from gitpython due to reliability issues; supports subprocess approach
- [Better Stack structlog guide](https://betterstack.com/community/guides/logging/structlog/) -- structlog setup patterns, level configuration
- [Enabling WAL mode (Simon Willison)](https://til.simonwillison.net/sqlite/enabling-wal-mode) -- WAL mode best practices

### Tertiary (LOW confidence)

- [Python programmatic pip freeze (pythontutorials.net)](https://www.pythontutorials.net/blog/how-to-retrieve-pip-requirements-freeze-within-python/) -- importlib.metadata approach to capturing installed packages; needs validation for completeness vs `pip freeze`
- [GitPython performance regression issue #906](https://github.com/gitpython-developers/GitPython/issues/906) -- Evidence of gitpython overhead, but issue is from 2019; current state unclear

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH -- All libraries verified via Context7 docs and PyPI. SQLite WAL mode is decades-proven. Structlog configuration patterns confirmed in official docs. Pydantic v2 frozen model pattern confirmed.
- Architecture: HIGH -- Incremental write pattern is standard (MLflow, every database-backed system). Two-store separation (SQLite metadata + filesystem artifacts) is the proven approach. Atomic file writes are POSIX standard.
- Pitfalls: HIGH -- SQLite thread-safety, commit-per-scenario, YAML non-determinism, UUID collisions, and schema migration idempotency are all well-documented failure modes with verified mitigations.
- Checkpoint persistence: MEDIUM -- Interface designed based on standard ML checkpoint patterns, but actual FK backend checkpoint API is undocumented. Implementation will need adjustment when API details are known.

**Research date:** 2026-02-19
**Valid until:** 2026-03-19 (stable domain; 30-day validity)
