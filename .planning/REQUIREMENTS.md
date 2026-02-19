# Requirements: FK Quant Research Acceleration Platform

**Defined:** 2026-02-19
**Core Value:** A researcher can define a 50-200 scenario batch, walk away, and come back to a ranked leaderboard with full reproducibility metadata and a deployable model package for the winner.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Experiment Identity & Storage

- [ ] **IDENT-01**: Each batch run is assigned a unique batch_run_id (UUID) at creation time; each scenario within a batch gets a unique scenario_run_id
- [ ] **IDENT-02**: Each run's artifacts are stored in a structured directory (`artifacts/{batch_run_id}/`) with per-scenario subdirectories
- [ ] **IDENT-03**: Full config is serialized per run (scenario grid, batch config, CLI args, git SHA, seed) as `manifest.yaml`
- [ ] **IDENT-04**: Run metadata is persisted to a local SQLite database with queryable fields (batch_run_id, scenario_run_id, timestamp, status, scenario count, score summary)
- [ ] **IDENT-05**: Researcher can list past runs with summary metrics via CLI (`list-runs`)
- [ ] **IDENT-06**: Researcher can compare two runs side-by-side aligned by scenario parameters via CLI (`compare-runs`)
- [ ] **IDENT-07**: Researcher can view detailed results for any past run via CLI (`show-run`)

### Configuration & Manifests

- [ ] **CONF-01**: Researcher defines experiments via YAML manifest files (scenario grid + batch config + scoring strategy + output paths)
- [ ] **CONF-02**: CLI accepts `--manifest path/to/experiment.yaml` to run a batch from a versioned config
- [ ] **CONF-03**: Each manifest is content-hash versioned so identical configs produce the same hash
- [ ] **CONF-04**: Reproducibility metadata is captured automatically per run: random seed, git SHA, pip freeze, Python version, OS, backend URL
- [ ] **CONF-05**: Scenario grid supports constraint validation (positive-definite correlation matrices, sensible volatility ranges, dimension-compatible option types)
- [ ] **CONF-06**: Invalid parameter combinations are rejected at pre-flight with clear error messages before any simulation is submitted
- [ ] **CONF-07**: YAML manifests support both PDE parameter sweeps and model/architecture sweeps as first-class axes
- [ ] **CONF-08**: All schemas are versioned from day one: manifest_schema_version, result_schema_version, and SQLite DB migration version tracked explicitly

### Execution

- [ ] **EXEC-01**: Batch simulations execute concurrently with configurable concurrency limit (e.g., 10-20 simultaneous polls)
- [ ] **EXEC-02**: Each completed scenario result is written to disk immediately (incremental writes, not batch-at-end)
- [ ] **EXEC-03**: If the process crashes mid-batch, completed results are preserved on disk
- [ ] **EXEC-04**: Researcher can resume an interrupted batch via CLI (`resume-batch`); resume is idempotent — completed scenarios are never rerun unless `--force` is specified
- [ ] **EXEC-05**: Failed individual simulations are recorded with error details, not silently dropped
- [ ] **EXEC-06**: Batch execution survives transient backend errors with configurable retry logic (backoff, max retries)
- [ ] **EXEC-07**: A 50-200 scenario batch can run unattended and complete without manual intervention (SLO: >=95% scenario success rate, max 3 retries per scenario, wall time <= 2x theoretical sequential time / concurrency limit)

### Results & Analysis

- [ ] **RSLT-01**: All run results conform to a structured schema with required fields: status, train_loss, grad_norm, runtime_seconds, error_stats, rank_score
- [ ] **RSLT-02**: Result schema is validated (Pydantic) before writing; malformed results are flagged, not silently accepted
- [ ] **RSLT-03**: Structured logging replaces all print() calls with configurable log levels (DEBUG, INFO, WARNING, ERROR)
- [ ] **RSLT-04**: CLI supports `--log-level` flag to control verbosity
- [ ] **RSLT-05**: Scoring is pluggable: researcher can select from built-in scorers or provide a custom scoring function via config
- [ ] **RSLT-06**: Built-in scorers include: loss-based (current), convergence-rate-based, and Pareto multi-objective
- [ ] **RSLT-07**: Convergence diagnostics detect oscillating loss, gradient explosion, and stagnation patterns per scenario
- [ ] **RSLT-08**: Each scenario result includes a convergence health label: healthy, oscillating, stagnating, or exploding
- [ ] **RSLT-09**: Leaderboard output includes convergence health alongside rank score

### Model Packaging

- [ ] **PKG-01**: Researcher can export the winning run as a model package via CLI (`export-model`)
- [ ] **PKG-02**: Model package contains: checkpoint/weights (sourced from FK PINN backend's checkpoint persistence API), exact training config, scenario config, seed, environment metadata
- [ ] **PKG-03**: Model package contains validation summary: final metrics, convergence health, acceptance threshold results
- [ ] **PKG-04**: Model package is a self-contained directory with a manifest describing all contents
- [ ] **PKG-05**: Model package includes enough metadata to reproduce the exact training run from scratch

### Extensibility

- [ ] **EXT-01**: New PDE problem types can be added without modifying orchestrator internals (ProblemSpec protocol)
- [ ] **EXT-02**: ProblemSpec defines: parameter schema, scenario generator, scorer, and validator per problem type
- [ ] **EXT-03**: Platform ships with built-in problem types: black_scholes, harmonic_oscillator
- [ ] **EXT-04**: Problem type is selectable via manifest `problem_id` field

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Serving & Deployment

- **SERV-01**: Winning model package can be loaded by an inference service endpoint
- **SERV-02**: Model registry with lifecycle stages (staging, production, archived)

### Advanced Analysis

- **ANAL-01**: Statistical significance testing on matched scenario pairs across runs (paired t-test, Wilcoxon)
- **ANAL-02**: Domain-specific validation gates (PDE residual convergence, boundary condition satisfaction, MC error bounds)

### Scaling

- **SCAL-01**: Support multiple local backends via round-robin distribution
- **SCAL-02**: Cloud/distributed execution backend support

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web dashboard / GUI | Solo researcher in terminal + notebook workflow; CLI + CSV/JSON artifacts sufficient for v1 |
| Real-time training metric streaming | Requires WebSocket/SSE infrastructure and backend changes; polling-based progress sufficient |
| Multi-user collaboration | Solo use case for v1; git-based sharing natural for team transition |
| Cloud/distributed execution | Local-first constraint; optimize local throughput first |
| Auto-ML / neural architecture search | PINN architecture constrained by physics; researcher judgment is the valuable input |
| Notebook-native experiment definition | Root cause of reproducibility problem this platform solves |
| Plugin marketplace / extension system | Solo researcher; direct Python extensibility (callables) is sufficient |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| IDENT-01 | TBD | Pending |
| IDENT-02 | TBD | Pending |
| IDENT-03 | TBD | Pending |
| IDENT-04 | TBD | Pending |
| IDENT-05 | TBD | Pending |
| IDENT-06 | TBD | Pending |
| IDENT-07 | TBD | Pending |
| CONF-01 | TBD | Pending |
| CONF-02 | TBD | Pending |
| CONF-03 | TBD | Pending |
| CONF-04 | TBD | Pending |
| CONF-05 | TBD | Pending |
| CONF-06 | TBD | Pending |
| CONF-07 | TBD | Pending |
| CONF-08 | TBD | Pending |
| EXEC-01 | TBD | Pending |
| EXEC-02 | TBD | Pending |
| EXEC-03 | TBD | Pending |
| EXEC-04 | TBD | Pending |
| EXEC-05 | TBD | Pending |
| EXEC-06 | TBD | Pending |
| EXEC-07 | TBD | Pending |
| RSLT-01 | TBD | Pending |
| RSLT-02 | TBD | Pending |
| RSLT-03 | TBD | Pending |
| RSLT-04 | TBD | Pending |
| RSLT-05 | TBD | Pending |
| RSLT-06 | TBD | Pending |
| RSLT-07 | TBD | Pending |
| RSLT-08 | TBD | Pending |
| RSLT-09 | TBD | Pending |
| PKG-01 | TBD | Pending |
| PKG-02 | TBD | Pending |
| PKG-03 | TBD | Pending |
| PKG-04 | TBD | Pending |
| PKG-05 | TBD | Pending |
| EXT-01 | TBD | Pending |
| EXT-02 | TBD | Pending |
| EXT-03 | TBD | Pending |
| EXT-04 | TBD | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 0
- Unmapped: 36

---
*Requirements defined: 2026-02-19*
*Last updated: 2026-02-19 after initial definition*
