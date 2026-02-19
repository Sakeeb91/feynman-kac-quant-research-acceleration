# Project Research Summary

**Project:** Feynman-Kac Quant Research Acceleration Platform
**Domain:** Local-first ML experiment management for PINN-based quant research
**Researched:** 2026-02-19
**Confidence:** HIGH

## Executive Summary

This is a local-first experiment management platform for a solo quantitative researcher running Physics-Informed Neural Network (PINN) solvers for financial PDEs (Black-Scholes and related). The current codebase is a functional but fragile prototype: it submits scenarios, polls results, scores them, and exports CSV — but loses all progress on crash, cannot resume interrupted batches, tracks no reproducibility metadata, and runs every job sequentially even though the FK PINN backend is stateless and HTTP-based. The recommended approach is an incremental hardening of this prototype rather than a rewrite: layer in a SQLite-backed durable task queue, a structured artifact directory, Pydantic-validated YAML manifests, async concurrent polling, and a pluggable scoring system — in that order, preserving all existing working code at every step.

The highest-impact single change is making batch execution durable and concurrent. A 100-scenario batch that currently takes 50+ hours (sequential polling) can complete in 1-3 hours with concurrent async polling (AnyIO + httpx). Combined with crash recovery, this transforms the "walk away and hope" workflow into a reliable "submit and come back" workflow. The second most critical area is reproducibility: recent research (arXiv:2505.10949) establishes that FP32 vs FP64 precision is a primary PINN failure mode, not an implementation detail — experiments are scientifically invalid if precision is not recorded and controlled. The entire value proposition of the platform depends on getting these two foundations right before adding any features.

The key risk is over-engineering. MLOps tooling literature describes team-scale infrastructure (distributed queuing, cloud storage, multi-user auth, model registries). Every one of those patterns is wrong for this use case. The complexity budget is strictly: Python asyncio + SQLite + local filesystem + YAML manifests. Every proposed dependency must justify itself against the question "what pain point does this solve that a Python script and SQLite cannot?" Phase-by-phase scope control is the primary execution risk.

## Key Findings

### Recommended Stack

The existing codebase uses Python 3.10, frozen dataclasses, `requests`, argparse, and `print()` — a solid foundation that needs targeted upgrades rather than replacement. The critical additions are AnyIO (structured async concurrency for concurrent polling), httpx (async HTTP client to replace `requests`), Pydantic v2 (validated manifests and result schemas), and SQLite via the Python stdlib (durable state store). Typer replaces argparse and Rich replaces bare print statements.

**Core technologies:**
- **Python >=3.11**: Upgraded from 3.10 for native `asyncio.TaskGroup` support; AnyIO works on 3.10 as a fallback if constraint exists
- **AnyIO >=4.12.1**: Structured async concurrency for concurrent scenario polling; strict superset of `asyncio.TaskGroup` with cancel scope control
- **httpx >=0.28.0**: Async HTTP client replacing `requests`; nearly identical API, enables concurrent batch execution
- **Pydantic >=2.12.5 + pydantic-settings >=2.13.0**: Validated, serializable manifest and result models; replaces frozen dataclasses
- **SQLite (stdlib)**: Zero-dependency ACID-compliant durable store; experiment metadata, run state, durable task queue; proven by MLflow's own local tracking
- **PyYAML >=6.0.3**: YAML manifest parsing; human-authored, diffable, git-versionable experiment definitions
- **Typer >=0.21.0 + Rich >=14.2.0**: CLI framework with progress bars and leaderboard tables; replaces argparse + print()
- **structlog >=25.5.0**: Structured JSON logging tied to run IDs; logs are research data, not debug noise
- **uv >=0.10.4**: Package management (10-100x faster than pip); Ruff, mypy, pytest already in project — bump versions

**What NOT to use:** Celery (wrong tool for local HTTP polling), Hydra (owns your CLI, conflicts with Typer), W&B/Neptune (cloud SaaS, violates local-first constraint), DVC (over-engineered for small YAML manifests), Sacred (abandoned, no Python 3.12+), MongoDB/PostgreSQL (server-based, operational overhead).

### Expected Features

The feature landscape spans three tiers. The P1 features are the core "define, run, rank, reproduce" loop — without them the platform is just the existing prototype with polish. P2 features add analytical power once the core loop is proven with real research batches. P3 features are v2+ when a serving endpoint exists.

**Must have (P1 — table stakes for v1.0):**
- Experiment run IDs + artifact directory (`artifacts/{run_id}/`) — foundation for everything; runs are unreferenceable without this
- Full config capture per run (scenario grid + batch config + CLI args + git SHA + seed) — serialized to `artifacts/{run_id}/manifest.yaml`
- YAML experiment manifests — move experiment definition from CLI args to versionable config files committed to git
- Structured result schema (Pydantic `RunResult` models) — consistent columns regardless of backend response quirks
- Failure handling + incremental result writes — checkpoint simulation IDs; resume on crash; write results as they complete
- Concurrent async batch execution — single highest-impact throughput feature; 10-50x speedup for batches >10 scenarios
- Logging and observability — replace `print()` with structured logging; `--log-level` flag

**Should have (P2 — after P1 is proven with real batches):**
- Configurable scoring/ranking — pluggable scorer protocol; decomposed metrics (PDE residual, boundary loss, initial condition loss, val loss)
- Cross-run comparison CLI (`compare-runs run_id_1 run_id_2`)
- Convergence diagnostics — detect oscillation, gradient explosion, stagnation patterns automatically
- Scenario grid DSL with constraints — pre-flight rejection of infeasible parameter combinations (non-positive-definite correlations, etc.)
- Reproducibility metadata (full env capture) — Python version, pip freeze, CUDA version, hardware identifier, dtype
- Problem-type extensibility — `ProblemSpec` protocol for non-Black-Scholes problems

**Defer to v2+:**
- Model packaging (requires serving endpoint)
- Statistical significance testing (requires enough runs to be meaningful)
- Domain-specific validation gates (deep PDE validation logic)
- Web dashboard (only if CLI + notebook analysis proves insufficient)
- Model registry with lifecycle stages

**Anti-features to avoid building:** Web dashboard, real-time metric streaming, multi-user collaboration, cloud/distributed execution, Auto-ML, notebook-native experiment definition, plugin marketplace. All of these add complexity without value for a solo local-first researcher.

### Architecture Approach

The recommended architecture has five layers: Interface (CLI + optional library API), Orchestration (Experiment Engine + Config Manager), Execution (Run Executor + FK PINN Client), Storage (SQLite Metadata Store + Filesystem Artifact Store), and Reporting. The existing `FKPinnClient`, `compute_score`, `write_csv`, and `cli.py` are preserved at every stage — new code wraps and extends, it does not replace working abstractions.

**Major components:**
1. **Config Manager** (`config/`) — Loads and validates YAML manifests; computes SHA-256 content hash for manifest versioning; produces frozen Pydantic config objects; merges CLI overrides. Config is immutable after loading — the manifest hash is the reproducibility anchor.
2. **Experiment Engine + State Machine** (`engine/`) — Governs experiment lifecycle through explicit state transitions (CREATED → VALIDATED → QUEUED → RUNNING → COMPLETING → COMPLETED | FAILED), persisted to SQLite. Coordinates config → queue → execution → reporting pipeline.
3. **Durable Task Queue** (`store/queue.py`) — SQLite-backed queue tracking each scenario run as a task (PENDING → IN_FLIGHT → COMPLETED | FAILED). On restart, `recover_in_flight()` moves abandoned tasks back to PENDING. This is the crash recovery mechanism.
4. **Metadata Store** (`store/metadata.py`) — Single SQLite database (`experiments.db`) with tables for experiments, runs, params, metrics, and task_queue. Schema modeled after MLflow's proven design. Append-only metrics table.
5. **Artifact Store** (`store/artifacts.py`) — Filesystem directory tree: `artifacts/{experiment_id}/{run_id}/` containing config_snapshot.json, metrics.csv, result.json, reproducibility.json. Metadata Store references Artifact Store paths but does not store binary data.
6. **Run Executor** (`engine/executor.py`) — Claims tasks from queue, submits to FK PINN backend via existing `FKPinnClient`, polls concurrently using AnyIO task groups, handles retries with exponential backoff, writes results to both stores.
7. **Reporting** (`reporting.py`, extended) — Reads completed run records from Metadata Store, scores with pluggable scorer, generates leaderboard CSV, supports multi-experiment comparison. Read-only from Metadata Store; never mutates run state.

**Key patterns:** Experiment State Machine (survives crashes), Durable Task Queue with SQLite (crash recovery), Two-Store Separation (metadata queryable, artifacts on filesystem), Content-Addressed Manifest Versioning (SHA-256 hash as reproducibility anchor).

### Critical Pitfalls

1. **Polling-Based Orchestration Loses Long-Running Experiments** — The current 30-minute timeout is too short for high-dimensional PINN jobs (1-4 hours). Sequential collection means one timeout discards all previous results. Fix: decouple submission from collection; persist job IDs to SQLite immediately; per-job error isolation. Address in Phase 1.

2. **In-Memory State Creates Total Data Loss** — `run_batch()` holds all state in Python lists. Any process termination (Ctrl-C, OOM, SSH disconnect, laptop sleep) loses everything. For overnight weekend batches, this is catastrophic. Fix: write-ahead logging to SQLite; append-only state schema; resume on startup. Address in Phase 1 — prerequisite to everything else.

3. **FP32/FP64 Precision Blindness** — This is PINN-specific and non-obvious: FP32 causes L-BFGS optimizers to declare false convergence near machine epsilon (1.19e-7), trapping the model in a "failure phase." Researchers comparing FP32 and FP64 runs on the same leaderboard are comparing invalid apples-to-oranges data. Fix: make `dtype` a first-class field in `Scenario`; default to FP64; flag runs converging near FP32 machine epsilon. Address in Phase 2 (manifest schema design).

4. **Naive Scoring Hides Real Convergence Quality** — `train_loss + 0.01 * abs(grad_norm)` has no scientific basis. The 0.01 weight is arbitrary; `val_loss` is captured but never used; all failures are scored equally (infinity). Fix: decompose metrics (PDE residual, boundary loss, IC loss, val loss); pluggable scorer protocol; Pareto multi-objective ranking. Address in Phase 2-3.

5. **Overengineering Beyond Solo Researcher Needs** — Enterprise MLOps patterns (distributed queuing, cloud storage, multi-user auth, model registries) are wrong for this use case. Every dependency must justify itself. Address in all phases as a continuous discipline.

## Implications for Roadmap

Based on combined research, the architecture's own build-order analysis (ARCHITECTURE.md) directly maps to phases. The dependency graph is strict: storage cannot be built after engine; engine cannot be built after execution hardening.

### Phase 1: Durable Execution Foundation

**Rationale:** The two most critical pitfalls (crash recovery and in-memory state loss) must be fixed before any other feature is useful. Without crash recovery, all downstream features (artifact management, reproducibility, comparison) cannot be trusted. This phase transforms the prototype from "fragile script" to "reliable local tool."

**Delivers:**
- SQLite metadata store with experiment/run/task_queue schema
- Filesystem artifact store with `artifacts/{experiment_id}/{run_id}/` layout
- Durable task queue with `recover_in_flight()` on startup
- Experiment run IDs assigned at creation
- Incremental result writes (results written as each scenario completes)
- Basic failure isolation (failed scenario does not abort batch)
- Structured logging replacing `print()` statements

**Addresses (FEATURES.md):** Experiment run IDs + artifact directory, failure handling + incremental writes, logging and observability

**Avoids (PITFALLS.md):** Pitfall 1 (polling loses long-running experiments), Pitfall 4 (in-memory state data loss), Pitfall 6 (over-engineering — this phase uses only stdlib SQLite)

**Stack:** SQLite (stdlib), structlog, platformdirs; extend existing orchestrator.py

### Phase 2: Domain Models, Manifests, and Concurrent Execution

**Rationale:** Once the storage layer exists, domain models and YAML manifests can be built against it. Concurrent execution is the single highest-throughput improvement and belongs here because it requires the durable queue from Phase 1 (without crash recovery, concurrency loses more work on failure than sequential execution). Reproducibility metadata — including FP32/FP64 dtype — must be in the manifest schema before any experiment results are trusted.

**Delivers:**
- Pydantic models for Scenario, BatchConfig, RunResult, RunManifest (replacing frozen dataclasses)
- YAML experiment manifest loader + Pydantic validator
- Content-addressed manifest versioning (SHA-256 hash)
- Reproducibility metadata capture: git SHA, Python version, dtype, seed, timestamps
- Concurrent async batch execution via AnyIO task groups + httpx
- CLI rewritten with Typer + Rich (progress bars, leaderboard tables)
- `pydantic-settings` for runtime config (base_url, poll intervals)

**Addresses (FEATURES.md):** Full config capture per run, YAML experiment manifests, structured result schema, concurrent async batch execution

**Avoids (PITFALLS.md):** Pitfall 2 (incomplete reproducibility), Pitfall 3 (naive scoring — schema designed here for decomposed metrics), Pitfall 5 (FP32/FP64 precision blindness — dtype as first-class manifest field)

**Stack:** Pydantic v2, pydantic-settings, AnyIO, httpx, PyYAML, Typer, Rich, gitpython

### Phase 3: Experiment Engine and State Machine

**Rationale:** With storage and models in place, the experiment lifecycle coordinator can be built. This formalizes the config → queue → execution → reporting pipeline as an explicit state machine, enabling reliable resume-after-crash and queryable experiment status.

**Delivers:**
- ExperimentState enum with validated transition table
- Experiment lifecycle coordinator (creates experiment record, advances states, coordinates pipeline)
- Resume capability: detect non-terminal experiments on startup, re-queue in-flight tasks
- New CLI commands: `status`, `list`, `show <experiment_id>`, `resume <experiment_id>`
- Experiment Engine wires together config → queue → executor → reporting

**Addresses (FEATURES.md):** Failure handling (resume path), logging and observability (queryable experiment status)

**Avoids (PITFALLS.md):** Pitfall 1 (polling — adaptive timeouts from stored historical runtimes), Pitfall 4 (in-memory state — all state in SQLite state machine)

**Stack:** Uses all Phase 1-2 components; no new external dependencies

### Phase 4: Scoring Overhaul and Cross-Run Comparison

**Rationale:** Once the core "define, run, rank, reproduce" loop is proven with real research batches, the scoring system needs to reflect actual PINN convergence quality rather than the arbitrary train_loss + 0.01 * grad_norm formula. This phase also adds cross-run comparison — the feature that turns individual batches into a systematic research program.

**Delivers:**
- Pluggable scorer protocol (Python callable or config-specified)
- Decomposed metrics stored separately: PDE residual loss, boundary loss, IC loss, val loss, gradient stability
- Default scorers: loss-based, convergence-rate, Pareto multi-objective
- Cross-run comparison CLI (`compare-runs run_id_1 run_id_2`) with delta reporting
- Convergence diagnostics: oscillation detection, gradient explosion flag, stagnation detection
- FP32 precision-limited flag (loss converges near 1e-7)
- Leaderboard with drill-down into decomposed metrics

**Addresses (FEATURES.md):** Configurable scoring/ranking, cross-run comparison, convergence diagnostics

**Avoids (PITFALLS.md):** Pitfall 3 (naive scoring), Pitfall 5 (FP32/FP64 — precision-aware diagnostics)

**Stack:** No new external dependencies; builds on Pydantic models from Phase 2

### Phase 5: Advanced Scenario Management and Extensibility

**Rationale:** Once multiple runs exist and comparison is working, the scenario generation layer becomes a bottleneck. Cartesian product explosions are a real performance trap (5 dimensions × 5 values = 3,125 scenarios at 30 min each = 65 days). This phase adds constraint-based scenario filtering, adaptive sampling hints, and problem-type extensibility for non-Black-Scholes problems.

**Delivers:**
- Scenario grid DSL with `constraints:` section in YAML manifests
- Pre-flight validation: positive-definite correlation check, vol range check, dim-compatible option types
- Scenario count warning with explicit confirmation required above threshold (e.g., 50 scenarios)
- Latin hypercube / Sobol sampling as alternative to full Cartesian product
- `ProblemSpec` protocol for problem-type extensibility
- Built-in problem types: `black_scholes` (existing), `harmonic_oscillator` (new)
- Full environment reproducibility bundle: pip freeze, CUDA version, hardware identifier

**Addresses (FEATURES.md):** Scenario grid DSL with constraints, reproducibility metadata (full), problem-type extensibility

**Avoids (PITFALLS.md):** Cartesian product explosion (performance trap), overengineering (ProblemSpec is a Python protocol, not a plugin marketplace)

**Stack:** No new external dependencies beyond Phase 1-4

### Phase Ordering Rationale

- **Storage before models before engine before execution:** Strict dependency graph from ARCHITECTURE.md. Each phase produces a system that is worse than production but better than the last.
- **Concurrent execution in Phase 2 not Phase 1:** Requires durable queue (Phase 1) for safe concurrent crash recovery. Concurrent execution without crash recovery loses more work than sequential execution.
- **Scoring overhaul after core loop proven:** Cannot validate a scoring formula until you have real research batches producing results. Building a sophisticated scorer against synthetic data is premature.
- **Extensibility last:** Problem-type extensibility requires stable Pydantic models (Phase 2), stable scoring protocols (Phase 4), and stable manifest schema (Phase 2). Building it before these abstractions exist means building it twice.
- **Existing code preserved at every phase:** `FKPinnClient`, `compute_score`, `write_csv` remain importable and functional throughout. This is a constraint, not an aspiration — regression is not acceptable.

### Research Flags

Phases likely needing deeper `/gsd:research-phase` during planning:

- **Phase 2 (Concurrent Execution):** AnyIO task group configuration for HTTP polling specifically — optimal concurrency limits, backpressure handling, cancellation behavior on partial failure. Standard asyncio patterns may not translate directly.
- **Phase 2 (Reproducibility Metadata):** FP32/FP64 dtype verification from FK PINN backend — requires understanding whether the backend reports actual precision used or only what was requested. Integration-specific research needed.
- **Phase 4 (Scoring):** Decomposed PINN metrics availability from FK PINN backend — what metric keys are actually returned? Are PDE residual, boundary loss, IC loss, and val loss separate keys or must they be inferred from `train_loss`?
- **Phase 5 (Sampling):** Latin hypercube / Sobol implementation — `scipy.stats.qmc` is the standard approach but adds scipy as a dependency. Needs evaluation against the complexity budget.

Phases with well-documented patterns (skip research-phase):

- **Phase 1 (Storage):** SQLite schema design and WAL mode — standard patterns, high confidence. MLflow schema is the reference implementation.
- **Phase 3 (State Machine):** Python enum-based state machine — standard pattern. `transitions` library optional; pure enum + dict transition table is simpler and sufficient.
- **Phase 4 (Comparison CLI):** Cross-run comparison data flow — reads from Metadata Store, aligns by scenario params, computes deltas. Standard data manipulation, no research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified via PyPI; Context7 docs confirmed for Pydantic and AnyIO; alternatives evaluated and rejected with rationale |
| Features | HIGH | Cross-referenced against MLflow, W&B, Optuna, DVC, Neptune, DeepXDE, Modulus; feature dependencies explicitly mapped; MVP clearly scoped |
| Architecture | HIGH | Patterns verified against MLflow (two-store), Sacred (lifecycle observer), persist-queue (durable SQLite queue); build order derived from strict dependency graph |
| Pitfalls | HIGH | Critical pitfalls backed by peer-reviewed sources (arXiv, NeurIPS, SciPy Proceedings); FP32/FP64 finding is 2025 research, directly applicable |

**Overall confidence:** HIGH

### Gaps to Address

- **FK PINN backend metric schema:** The client already shows API instability (`metrics.get("loss", metrics.get("train_loss"))`). Need to audit what metric keys the backend actually returns and which are stable vs. version-dependent. Define a canonical adapter layer before building the structured result schema.
- **FK PINN backend precision reporting:** Does the backend return actual dtype used (FP32 vs FP64) in the response, or only what was requested? This determines whether precision verification is possible without backend changes.
- **FK PINN backend job lifecycle:** Does a 404 on a submitted simulation_id mean "never existed" or "expired"? This determines the "heartbeat check" implementation for detecting backend restarts during long polls.
- **Actual PINN convergence time distribution:** The 30-minute timeout in the current code is a guess. Need empirical data on p50, p95, p99 runtimes for Black-Scholes across the target dimension range (2D to 50D) to set adaptive timeouts.
- **Schema migration strategy:** The manifest schema will evolve. A version field must be in the manifest from Phase 1 even if no migration scripts are written yet. Define the version field and migration convention before writing the first schema.

## Sources

### Primary (HIGH confidence)
- Context7 `/pydantic/pydantic` — BaseModel, frozen config, dataclass interop
- Context7 `/agronholm/anyio` — task groups, structured concurrency
- [Pydantic PyPI](https://pypi.org/project/pydantic/) — v2.12.5 verified
- [AnyIO PyPI](https://pypi.org/project/anyio/) — v4.12.1 verified
- [MLflow Tracking documentation](https://mlflow.org/docs/latest/ml/tracking/) — two-store architecture, schema design
- [MLflow SQLite local tracking](https://mlflow.org/docs/latest/ml/tracking/tutorials/local-database/) — local tracking pattern
- [persist-queue (PyPI)](https://pypi.org/project/persist-queue/) — SQLite durable queue, WAL mode, crash recovery
- [Sacred experiment framework docs](https://sacred.readthedocs.io/en/stable/observers.html) — lifecycle observer pattern
- [FP64 is All You Need: Rethinking Failure Modes in PINNs (arXiv:2505.10949)](https://arxiv.org/html/2505.10949v1) — definitive FP32/FP64 PINN precision analysis
- [Characterizing possible failure modes in PINNs (NeurIPS 2021)](https://proceedings.neurips.cc/paper/2021/file/df438e5206f31600e6ae4af72f2725f1-Paper.pdf) — systematic PINN failure mode analysis
- [State design pattern (Refactoring Guru)](https://refactoring.guru/design-patterns/state) — FSM pattern reference

### Secondary (MEDIUM confidence)
- [Neptune.ai MLOps architecture guide](https://neptune.ai/blog/mlops-architecture-guide) — standard architecture layers
- [Neptune.ai best ML experiment tracking tools](https://neptune.ai/blog/best-ml-experiment-tracking-tools) — ecosystem survey
- [MLOps Anti-Patterns (arXiv:2107.00079)](https://arxiv.org/abs/2107.00079) — common over-engineering risks
- [Springer - ML experiment management tools empirical study (2024)](https://link.springer.com/article/10.1007/s10664-024-10444-w) — adoption barriers and feature usage patterns
- [Experience report of PINNs in fluid simulations (SciPy Proceedings)](https://proceedings.scipy.org/articles/majora-212e5952-005) — PINN-specific failure modes
- [Hydra docs](https://hydra.cc/) — evaluated and rejected for this project
- [DeepXDE GitHub](https://github.com/lululxvi/deepxde) — PINN framework feature set reference
- [Ploomber: Who needs MLflow when you have SQLite?](https://ploomber.io/blog/experiment-tracking/) — SQLite vs MLflow for small teams

### Tertiary (LOW confidence)
- [MLXP: A Framework for Conducting Replicable Experiments (arXiv:2402.13831)](https://arxiv.org/html/2402.13831v2) — lightweight experiment management patterns; needs validation against FK PINN specifics
- [QuantConnect](https://www.quantconnect.com/) — quant platform validation patterns; indirect applicability to PINN validation gates

---
*Research completed: 2026-02-19*
*Ready for roadmap: yes*
