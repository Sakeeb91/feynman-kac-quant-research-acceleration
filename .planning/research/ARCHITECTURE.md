# Architecture Research

**Domain:** Local-first ML experiment management platform for PINN-based quant research
**Researched:** 2026-02-19
**Confidence:** HIGH (architecture patterns well-established across MLflow, Sacred, DVC; adapted to local-first constraints)

## Standard Architecture

### System Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                         Interface Layer                              │
│  ┌──────────┐  ┌──────────────────┐                                  │
│  │   CLI    │  │  Programmatic    │                                  │
│  │ (argparse)│  │  API (library)  │                                  │
│  └─────┬────┘  └───────┬─────────┘                                  │
│        └───────┬───────┘                                             │
├────────────────┼─────────────────────────────────────────────────────┤
│                │        Orchestration Layer                          │
│  ┌─────────────▼──────────────┐  ┌──────────────────────────┐       │
│  │     Experiment Engine      │  │    Config Manager         │       │
│  │ (state machine, lifecycle) │  │ (YAML manifest loading,   │       │
│  │                            │◄─┤  validation, versioning)  │       │
│  └─────────┬──────────────────┘  └──────────────────────────┘       │
│            │                                                         │
│  ┌─────────▼──────────────┐  ┌──────────────────────────────┐       │
│  │     Task Queue         │  │    Scenario Generator         │       │
│  │ (durable, SQLite-      │  │ (cross-product, filtering,   │       │
│  │  backed, restartable)  │  │  deduplication)               │       │
│  └─────────┬──────────────┘  └──────────────────────────────┘       │
├────────────┼─────────────────────────────────────────────────────────┤
│            │        Execution Layer                                  │
│  ┌─────────▼──────────────┐  ┌──────────────────────────────┐       │
│  │     Run Executor       │  │    FK PINN Client             │       │
│  │ (submit, poll, retry,  │──▶ (HTTP wrapper, existing)     │       │
│  │  collect results)      │  └──────────────┬───────────────┘       │
│  └─────────┬──────────────┘                 │                        │
│            │                                │ HTTP                   │
├────────────┼────────────────────────────────┼────────────────────────┤
│            │        Storage Layer           │                        │
│  ┌─────────▼──────────────┐  ┌──────────────────────────────┐       │
│  │   Metadata Store       │  │    Artifact Store             │       │
│  │ (SQLite: experiments,  │  │ (filesystem: CSVs, configs,  │       │
│  │  runs, params, metrics,│  │  checkpoints, model packages,│       │
│  │  state, queue)         │  │  reproducibility bundles)     │       │
│  └────────────────────────┘  └──────────────────────────────┘       │
├─────────────────────────────────────────────┼────────────────────────┤
│                                             │                        │
│  ┌────────────────────────────────────────┐ │                        │
│  │          Reporting Layer               │ │                        │
│  │  (scoring, ranking, CSV export,        │ │                        │
│  │   leaderboard generation, comparison)  │ │                        │
│  └────────────────────────────────────────┘ │                        │
│                                             ▼                        │
│                                    ┌────────────────┐                │
│                                    │  FK PINN       │                │
│                                    │  Backend       │                │
│                                    │  (external)    │                │
│                                    └────────────────┘                │
└───────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Config Manager** | Load, validate, version YAML experiment manifests; merge overrides from CLI; produce frozen config objects | YAML loader + Pydantic/dataclass validation + content-hash for manifest identity |
| **Experiment Engine** | Govern experiment lifecycle through state machine; coordinate config -> queue -> execution -> reporting pipeline | State machine (enum-based or `transitions` library) with SQLite-persisted state |
| **Task Queue** | Durably enqueue scenario runs; survive process crashes and restarts; track pending/in-flight/completed items | SQLite-backed queue (persist-queue `SQLiteAckQueue` or custom table in shared SQLite DB) |
| **Scenario Generator** | Produce scenario lists from manifest definitions; cross-product expansion, filtering, deduplication against prior runs | Pure functions operating on config objects; existing `generate_black_scholes_scenarios` pattern extended |
| **Run Executor** | Submit individual scenarios to FK PINN backend, poll for completion, handle retries and timeouts, collect raw results | Wraps existing `FKPinnClient`; adds retry logic (tenacity/exponential backoff), concurrent polling |
| **FK PINN Client** | HTTP communication with external solver backend | Existing `FKPinnClient` (frozen dataclass + requests); preserved as-is |
| **Metadata Store** | Persist experiment definitions, run records, parameters, metrics, state transitions, queue state | Single SQLite database file; schema modeled after MLflow's experiments/runs/params/metrics tables |
| **Artifact Store** | Store and retrieve experiment outputs: CSV results, config snapshots, model checkpoints, reproducibility bundles | Filesystem directory tree organized by experiment_id/run_id; content-addressed where appropriate |
| **Reporting** | Score runs, rank results, generate leaderboards, export CSV/JSON summaries, compare across experiments | Existing `compute_score` + `write_csv` extended with configurable scoring and multi-experiment comparison |

## Recommended Project Structure

```
src/fk_quant_research_accel/
├── __init__.py               # Public API exports
├── cli.py                    # CLI entry point (existing, extended)
├── client.py                 # FK PINN HTTP client (existing, preserved)
├── orchestrator.py           # Batch orchestration (existing, refactored)
├── reporting.py              # Scoring and CSV export (existing, extended)
├── config/                   # Config management module
│   ├── __init__.py
│   ├── loader.py             # YAML manifest loading and validation
│   ├── schema.py             # Pydantic/dataclass models for manifests
│   └── versioning.py         # Content-hash based manifest versioning
├── engine/                   # Experiment lifecycle engine
│   ├── __init__.py
│   ├── states.py             # State enum and transition definitions
│   ├── experiment.py         # Experiment lifecycle coordinator
│   └── executor.py           # Run execution with retry and concurrency
├── store/                    # Storage layer
│   ├── __init__.py
│   ├── metadata.py           # SQLite metadata store (experiments, runs, metrics)
│   ├── artifacts.py          # Filesystem artifact store
│   ├── queue.py              # Durable task queue (SQLite-backed)
│   └── migrations.py         # Schema versioning for SQLite
└── models/                   # Domain models (extended from existing)
    ├── __init__.py
    ├── scenario.py           # Scenario dataclass (extracted from orchestrator)
    ├── batch.py              # BatchConfig dataclass (extracted from orchestrator)
    ├── run.py                # Run record model with full metadata
    └── manifest.py           # Experiment manifest model
```

### Structure Rationale

- **config/:** Isolated because manifest loading, validation, and versioning are a self-contained concern. Config objects flow into all other modules but config management itself has no downstream dependencies.
- **engine/:** Groups the state machine, lifecycle coordination, and execution logic. This is the "brain" of the system -- it reads config, manages queue, drives execution, and triggers reporting.
- **store/:** Unified storage layer with two backends (SQLite for metadata, filesystem for artifacts) behind clean interfaces. All persistence goes through this module, making it possible to test other components without touching disk.
- **models/:** Shared domain models used across all layers. Extracted from the current `orchestrator.py` to avoid circular dependencies between config, engine, and store.
- **Existing files preserved at top level:** `client.py`, `cli.py`, `reporting.py` remain at the package root because they are existing, working code. Refactoring them into subdirectories is unnecessary churn.

## Architectural Patterns

### Pattern 1: Experiment State Machine

**What:** Every experiment progresses through a finite set of states with explicit, validated transitions. State is persisted to SQLite so it survives process crashes.

**When to use:** Always. Every experiment lifecycle operation checks and advances state.

**Trade-offs:** Adds complexity vs. the current "just call run_batch()"; but prevents silent state corruption, enables resume-after-crash, and makes experiment status queryable.

**State diagram:**

```
                    ┌──────────┐
                    │ CREATED  │
                    └────┬─────┘
                         │ validate_config()
                         ▼
                    ┌──────────┐
           ┌───────│ VALIDATED │
           │       └────┬─────┘
           │            │ enqueue_scenarios()
           │            ▼
           │       ┌──────────┐
           │       │ QUEUED   │
           │       └────┬─────┘
           │            │ start_execution()
           │            ▼
           │       ┌──────────┐     timeout/error
           │       │ RUNNING  │──────────────┐
           │       └────┬─────┘              │
           │            │ all_runs_terminal() │
           │            ▼                    ▼
           │       ┌──────────┐        ┌──────────┐
           │       │COMPLETING│        │  FAILED  │
           │       └────┬─────┘        └──────────┘
           │            │ generate_report()    ▲
           │            ▼                      │
           │       ┌──────────┐                │
           │       │COMPLETED │                │
           │       └──────────┘                │
           │                                   │
           └───────────────────────────────────┘
                   validation_error()
```

**Example:**

```python
from enum import Enum

class ExperimentState(Enum):
    CREATED = "created"
    VALIDATED = "validated"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETING = "completing"
    COMPLETED = "completed"
    FAILED = "failed"

VALID_TRANSITIONS: dict[ExperimentState, set[ExperimentState]] = {
    ExperimentState.CREATED: {ExperimentState.VALIDATED, ExperimentState.FAILED},
    ExperimentState.VALIDATED: {ExperimentState.QUEUED, ExperimentState.FAILED},
    ExperimentState.QUEUED: {ExperimentState.RUNNING, ExperimentState.FAILED},
    ExperimentState.RUNNING: {ExperimentState.COMPLETING, ExperimentState.FAILED},
    ExperimentState.COMPLETING: {ExperimentState.COMPLETED, ExperimentState.FAILED},
    ExperimentState.COMPLETED: set(),  # terminal
    ExperimentState.FAILED: set(),     # terminal
}

def transition(current: ExperimentState, target: ExperimentState) -> ExperimentState:
    if target not in VALID_TRANSITIONS[current]:
        raise ValueError(f"Invalid transition: {current.value} -> {target.value}")
    return target
```

### Pattern 2: Durable Task Queue with SQLite

**What:** A persistent queue backed by SQLite that enqueues scenario runs, tracks their state (pending/in-flight/completed/failed), and survives process restarts. On restart, in-flight items are re-queued.

**When to use:** For all batch experiment execution. Replaces the current in-memory list of `(scenario, simulation_id)` tuples in `run_batch()`.

**Trade-offs:** SQLite adds a file dependency and slightly more complex code vs. in-memory list; but provides crash recovery, progress persistence, and the ability to resume interrupted batches.

**Example:**

```python
import sqlite3
from dataclasses import dataclass
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    experiment_id: str
    scenario_json: str
    status: TaskStatus
    simulation_id: str | None = None
    attempt: int = 0

class DurableQueue:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._ensure_schema()

    def enqueue(self, experiment_id: str, scenario_json: str) -> str:
        """Insert a pending task. Returns task_id."""
        ...

    def claim_next(self) -> TaskRecord | None:
        """Atomically move one PENDING task to IN_FLIGHT. Returns None if empty."""
        ...

    def complete(self, task_id: str, result_json: str) -> None:
        """Mark task as COMPLETED with result payload."""
        ...

    def fail(self, task_id: str, error: str) -> None:
        """Mark task as FAILED with error message."""
        ...

    def recover_in_flight(self) -> int:
        """On restart: move all IN_FLIGHT tasks back to PENDING. Returns count."""
        ...
```

### Pattern 3: Two-Store Separation (Metadata + Artifacts)

**What:** Separate metadata (structured, queryable) from artifacts (binary, large). Metadata lives in SQLite; artifacts live on the filesystem in a directory tree keyed by experiment_id and run_id.

**When to use:** Always. This is the standard pattern used by MLflow, Sacred, and every mature experiment tracker.

**Trade-offs:** Two storage backends to manage instead of one; but metadata queries are fast (SQL), artifacts can be large (model checkpoints), and each store can evolve independently.

**Data flow:**

```
Metadata Store (SQLite)              Artifact Store (filesystem)
┌────────────────────┐               ┌────────────────────────────┐
│ experiments        │               │ artifacts/                 │
│   id, name, state, │               │   {experiment_id}/         │
│   created_at,      │               │     manifest.yaml          │
│   manifest_hash    │               │     {run_id}/              │
│                    │               │       config_snapshot.json  │
│ runs               │               │       metrics.csv          │
│   id, experiment_id│──references──▶│       result.json          │
│   scenario_json,   │               │       checkpoint/          │
│   state, sim_id,   │               │         model.pt           │
│   started_at,      │               │         optimizer.pt       │
│   completed_at     │               │       reproducibility.json │
│                    │               │     leaderboard.csv        │
│ metrics            │               │     comparison_report.json │
│   run_id, key,     │               └────────────────────────────┘
│   value, step,     │
│   timestamp        │
│                    │
│ params             │
│   run_id, key,     │
│   value            │
│                    │
│ queue              │
│   task_id, status, │
│   experiment_id,   │
│   scenario_json,   │
│   attempt          │
└────────────────────┘
```

### Pattern 4: Content-Addressed Manifest Versioning

**What:** Each experiment manifest (YAML file defining scenarios, training config, scoring criteria) gets a content hash (SHA-256 of normalized YAML content). This hash serves as the manifest version and is stored with the experiment record.

**When to use:** Every time a manifest is loaded for execution.

**Trade-offs:** Requires normalizing YAML before hashing (key ordering, whitespace); but guarantees that two runs with the same manifest hash used identical configuration, enabling true reproducibility.

**Example:**

```python
import hashlib
import json

def manifest_hash(manifest_dict: dict) -> str:
    """Deterministic hash of manifest content."""
    canonical = json.dumps(manifest_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

## Data Flow

### Primary Experiment Lifecycle Flow

```
[User: CLI or API]
    │
    │  1. Load manifest (YAML file path or dict)
    ▼
[Config Manager]
    │  - Parse YAML
    │  - Validate against schema
    │  - Compute manifest content hash
    │  - Resolve overrides (CLI args merge)
    │  - Produce frozen config objects
    ▼
[Experiment Engine]
    │  2. Create experiment record in metadata store
    │     - experiment_id = UUID
    │     - manifest_hash = content hash
    │     - state = CREATED -> VALIDATED
    ▼
[Scenario Generator]
    │  3. Expand manifest into individual scenarios
    │     - Cross-product of parameter axes
    │     - Deduplication against completed runs (optional)
    │     - Filter by user criteria
    ▼
[Task Queue]
    │  4. Enqueue each scenario as a task
    │     - task_id = UUID
    │     - status = PENDING
    │     - state = VALIDATED -> QUEUED
    ▼
[Run Executor]                    [FK PINN Client]
    │  5. Claim tasks from queue       │
    │     - status = PENDING ->        │
    │       IN_FLIGHT                  │
    │  6. Submit to backend ──────────▶│──▶ FK PINN Backend
    │     - Store simulation_id        │      (external)
    │  7. Poll until terminal ◀────────│◀── HTTP response
    │  8. Collect result               │
    │  9. Mark task COMPLETED/FAILED   │
    │     - Write metrics to store     │
    │     - Write artifacts to disk    │
    │  10. Loop until queue empty      │
    ▼
[Experiment Engine]
    │  11. All tasks terminal
    │      - state = RUNNING -> COMPLETING
    ▼
[Reporting]
    │  12. Score and rank all runs
    │  13. Generate leaderboard CSV
    │  14. Write comparison artifacts
    │  15. state = COMPLETING -> COMPLETED
    ▼
[Artifact Store]
    │  16. All outputs organized under
    │      artifacts/{experiment_id}/
    ▼
[User: reads CSV, inspects artifacts, queries metadata]
```

### Crash Recovery Flow

```
[Process restarts]
    │
    ▼
[Experiment Engine]
    │  1. Query metadata store for non-terminal experiments
    │     (state in {QUEUED, RUNNING, COMPLETING})
    │
    ▼
[Task Queue]
    │  2. recover_in_flight()
    │     - All IN_FLIGHT tasks -> PENDING
    │     - Already-COMPLETED tasks preserved
    │
    ▼
[Run Executor]
    │  3. Resume from queue (only pending tasks remain)
    │     - Completed runs are NOT re-submitted
    │     - Failed runs MAY be retried (configurable)
    │
    ▼
[Normal flow continues from step 5 above]
```

### Key Data Flows

1. **Config -> Frozen Objects:** YAML manifest is loaded once, validated, hashed, and converted into immutable dataclass instances. These frozen objects flow downstream and are never mutated. The manifest hash is the reproducibility anchor.

2. **Queue -> Executor -> Store (write path):** The executor claims tasks from the queue, executes against the backend, and writes results to both the metadata store (structured metrics) and artifact store (raw output files). This is the hot path during experiment execution.

3. **Store -> Reporting (read path):** Reporting reads completed run records from the metadata store, computes scores, and writes aggregate artifacts (leaderboards, comparisons) to the artifact store. This is the post-execution analysis path.

4. **Metadata Store -> CLI (query path):** The CLI can query experiment status, list runs, show leaderboards, and inspect individual run details by reading from the metadata store. This enables `fk-research status`, `fk-research list`, `fk-research show <experiment_id>` commands.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-50 scenarios | Current architecture is fine. Single-threaded executor, in-memory accumulation. SQLite overhead is negligible. |
| 50-500 scenarios | Concurrent polling required. Use `concurrent.futures.ThreadPoolExecutor` with 5-10 workers. SQLite handles this with WAL mode. Stream results to disk incrementally. |
| 500-2000 scenarios | Batch submission with throttling. Add backpressure detection (if backend queue depth > threshold, pause submission). Consider partitioning large experiments into sub-experiments. |
| 2000+ scenarios | Beyond v1 scope. Would need distributed execution across multiple backends, sharded artifact storage, and potentially PostgreSQL instead of SQLite. |

### Scaling Priorities

1. **First bottleneck:** Sequential polling in `run_batch()`. Current code polls one simulation at a time. Fix: concurrent polling with thread pool. Expected improvement: 10-50x for batches > 10 scenarios.
2. **Second bottleneck:** No crash recovery. Long-running batches (hours) are completely lost on process crash. Fix: durable task queue + metadata persistence. This is the highest-priority architectural change.

## Anti-Patterns

### Anti-Pattern 1: In-Memory-Only Experiment State

**What people do:** Track submitted simulations as a list of `(scenario, simulation_id)` tuples in memory (current implementation).
**Why it's wrong:** Any process crash, keyboard interrupt, or OOM kills ALL progress. For 200-scenario batches running 6+ hours, this is catastrophic. No way to resume, no way to inspect partial results.
**Do this instead:** Persist every state transition to SQLite. On restart, query for incomplete experiments and resume from the last checkpoint.

### Anti-Pattern 2: Coupling Config Loading with Execution

**What people do:** Parse CLI arguments directly into execution parameters within the same function (current `main()` in cli.py).
**Why it's wrong:** Makes it impossible to version configs, replay experiments, or compare configurations across runs. Config becomes ephemeral.
**Do this instead:** Separate config loading into a distinct phase that produces a frozen, hashable manifest object. Store the manifest alongside experiment results for full reproducibility.

### Anti-Pattern 3: Monolithic Orchestrator

**What people do:** Put scenario generation, submission, polling, result collection, and scoring all in one function (current `run_batch()`).
**Why it's wrong:** Cannot test, retry, or observe individual phases. Cannot resume from mid-batch. Cannot add new functionality (like concurrent polling) without rewriting the entire function.
**Do this instead:** Decompose into pipeline stages (generate -> enqueue -> execute -> collect -> score -> report) connected through the metadata store.

### Anti-Pattern 4: Flat Artifact Directory

**What people do:** Write all results to a single `artifacts/batch_results.csv` file.
**Why it's wrong:** Overwrites previous results. No way to associate artifacts with specific experiments. No place for model checkpoints, config snapshots, or reproducibility metadata.
**Do this instead:** Organize artifacts in a directory tree: `artifacts/{experiment_id}/{run_id}/`. Each experiment gets its own namespace. Config snapshots, metrics, and model outputs are co-located with the run that produced them.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| FK PINN Backend | HTTP client (existing `FKPinnClient`) | Preserve current interface; add retry wrapper and concurrent polling on top. Do NOT modify the client class itself. |
| Git (for code SHA) | `subprocess.run(["git", "rev-parse", "HEAD"])` | Capture at experiment creation time for reproducibility. Fail gracefully if not in a git repo. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Config Manager -> Engine | Frozen dataclass objects | Config produces; engine consumes. One-way data flow. No callbacks. |
| Engine -> Task Queue | Method calls on queue interface | Engine enqueues tasks and checks completion status. Queue is a service object injected into engine. |
| Engine -> Run Executor | Method calls; executor reads from queue | Executor is stateless; all state lives in queue and metadata store. |
| Run Executor -> FK PINN Client | Method calls (existing interface) | Executor wraps client with retry logic. Client interface unchanged. |
| Engine -> Metadata Store | SQL operations via store interface | Engine writes state transitions; reporting reads completed records. Store provides a clean Python API over raw SQL. |
| Engine -> Artifact Store | Filesystem operations via store interface | Engine and reporting write artifacts. Store handles directory creation and path resolution. |
| Reporting -> Metadata Store | Read-only queries | Reporting never mutates experiment/run state. It reads metrics, computes scores, and writes artifact files. |
| CLI -> Engine | Method calls | CLI is a thin layer that parses args, constructs config, and delegates to engine. |

## Build Order

The components have a clear dependency graph that dictates build order. Each phase produces a usable system when combined with the existing code.

```
Phase 1: Storage Layer (foundation -- everything else depends on this)
    │
    ├── Metadata Store (SQLite schema, CRUD operations for experiments/runs/metrics)
    ├── Artifact Store (directory management, path resolution)
    └── Queue (durable task queue with crash recovery)
    │
Phase 2: Domain Models + Config Management
    │
    ├── Extract Scenario/BatchConfig to models/ module
    ├── Add Run, Experiment, Manifest models
    ├── YAML manifest loader + validator
    └── Content-hash versioning
    │
Phase 3: Experiment State Machine + Engine
    │
    ├── State enum and transition table
    ├── Experiment lifecycle coordinator (orchestrates phases)
    └── Wires together: config -> queue -> executor -> reporting
    │
Phase 4: Execution Hardening
    │
    ├── Run Executor with retry logic (wraps FKPinnClient)
    ├── Concurrent polling (ThreadPoolExecutor)
    ├── Crash recovery (recover_in_flight on startup)
    └── Reproducibility metadata capture (git SHA, env, timestamps)
    │
Phase 5: Reporting + CLI Extension
    │
    ├── Extended scoring (configurable criteria, multi-metric)
    ├── Multi-experiment comparison
    ├── New CLI commands: status, list, show, resume
    └── Leaderboard generation with artifact references
```

**Phase ordering rationale:**

- **Storage first** because every other component needs somewhere to persist state. Without the metadata store and queue, the engine cannot track experiments and the executor cannot survive crashes.
- **Models + Config second** because the engine needs frozen config objects and domain models to work with. The existing `Scenario` and `BatchConfig` are extracted and extended here.
- **Engine third** because it coordinates all other components. It cannot be built until storage and models exist.
- **Execution hardening fourth** because it requires the engine (to manage lifecycle), the queue (to track tasks), and the store (to persist results). This is where the existing `run_batch()` logic gets decomposed and hardened.
- **Reporting + CLI last** because it consumes everything upstream. The existing `reporting.py` and `cli.py` continue to work throughout; this phase extends them rather than replacing them.

**Critical constraint:** The existing `FKPinnClient`, `Scenario`, `BatchConfig`, `compute_score`, and `write_csv` must remain functional and importable at every phase. New code wraps and extends; it does not replace working abstractions.

## Metadata Store Schema

Use a single SQLite database file (`experiments.db`) in the project's data directory. Schema modeled after MLflow's proven design, adapted for local-first use.

```sql
-- Core experiment tracking
CREATE TABLE experiments (
    id TEXT PRIMARY KEY,           -- UUID
    name TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,   -- SHA-256 prefix of normalized config
    state TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL,      -- ISO 8601
    updated_at TEXT NOT NULL,
    config_json TEXT NOT NULL,     -- Full frozen config snapshot
    git_sha TEXT,                  -- Code version at creation time
    python_version TEXT,
    notes TEXT
);

-- Individual scenario runs within an experiment
CREATE TABLE runs (
    id TEXT PRIMARY KEY,           -- UUID
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    scenario_json TEXT NOT NULL,   -- Frozen scenario parameters
    state TEXT NOT NULL DEFAULT 'pending',
    simulation_id TEXT,            -- FK PINN backend simulation ID
    attempt INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    artifact_path TEXT             -- Relative path under artifact store
);

-- Key-value parameters for each run
CREATE TABLE params (
    run_id TEXT NOT NULL REFERENCES runs(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (run_id, key)
);

-- Time-series metrics for each run (append-only)
CREATE TABLE metrics (
    run_id TEXT NOT NULL REFERENCES runs(id),
    key TEXT NOT NULL,
    value REAL NOT NULL,
    step INTEGER,
    timestamp TEXT NOT NULL
);

-- Durable task queue
CREATE TABLE task_queue (
    id TEXT PRIMARY KEY,           -- UUID
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    run_id TEXT NOT NULL REFERENCES runs(id),
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/in_flight/completed/failed
    priority INTEGER NOT NULL DEFAULT 0,
    claimed_at TEXT,
    completed_at TEXT,
    attempt INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error TEXT
);

CREATE INDEX idx_runs_experiment ON runs(experiment_id);
CREATE INDEX idx_runs_state ON runs(state);
CREATE INDEX idx_metrics_run ON metrics(run_id);
CREATE INDEX idx_queue_status ON task_queue(status);
CREATE INDEX idx_queue_experiment ON task_queue(experiment_id);
```

## Sources

- [MLflow Tracking documentation](https://mlflow.org/docs/latest/ml/tracking/) -- core entity model (experiments, runs, params, metrics, artifacts); two-store architecture (backend store + artifact store) -- **HIGH confidence**
- [MLflow database schema overview](https://www.restack.io/docs/mlflow-knowledge-mlflow-database-schema) -- schema tables (experiments, runs, params, metrics, tags, model_versions) and append-only metrics design -- **MEDIUM confidence** (secondary source)
- [persist-queue (PyPI)](https://pypi.org/project/persist-queue/) -- SQLite-backed durable queue with WAL mode, crash recovery, and ack semantics -- **HIGH confidence** (official package docs)
- [Sacred experiment framework](https://sacred.readthedocs.io/en/stable/observers.html) -- observer pattern for experiment lifecycle; decoupled logging via pluggable backends -- **HIGH confidence** (official docs)
- [Hydra configuration framework](https://hydra.cc/docs/intro/) -- YAML-based hierarchical config management with composition and CLI overrides -- **HIGH confidence** (official docs)
- [pytransitions/transitions](https://github.com/pytransitions/transitions) -- lightweight Python state machine library with transition callbacks -- **HIGH confidence** (official repo)
- [Neptune.ai MLOps architecture guide](https://neptune.ai/blog/mlops-architecture-guide) -- standard MLOps architecture layers and component responsibilities -- **MEDIUM confidence** (vendor blog, but well-sourced)
- [Neptune.ai ML experiment tracking tools](https://neptune.ai/blog/best-ml-experiment-tracking-tools) -- comparison of experiment management tools and their architectural approaches -- **MEDIUM confidence**
- [MLflow with SQLite local tracking](https://mlflow.org/docs/latest/ml/tracking/tutorials/local-database/) -- SQLite as local backend store for experiment tracking; schema creation via SQLAlchemy -- **HIGH confidence** (official MLflow docs)
- [State design pattern (Refactoring Guru)](https://refactoring.guru/design-patterns/state) -- finite state machine pattern; context + state objects + transition rules -- **HIGH confidence** (authoritative pattern reference)

---
*Architecture research for: local-first ML experiment management platform*
*Researched: 2026-02-19*
