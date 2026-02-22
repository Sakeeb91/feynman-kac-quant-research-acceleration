# Roadmap: FK Quant Research Acceleration Platform

## Overview

This roadmap transforms a fragile prototype into a reliable research acceleration platform across seven phases. The journey starts by making the existing codebase crash-safe and observable (durable storage, including checkpoint persistence), then layers on config-driven experiment definition with pre-flight validation (manifests), concurrent execution (the single biggest throughput gain), analytical power (scoring and diagnostics), researcher query tools (run analysis CLI), domain extensibility (new problem types), and finally model packaging for the winning runs. Every phase delivers a coherent capability that a researcher can verify, and each builds strictly on the foundations laid by prior phases.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Durable Storage Foundation** - Run identity, artifact directories, checkpoint persistence, SQLite metadata, crash-safe writes, structured logging
- [x] **Phase 2: YAML Manifests, Validation, and Domain Models** - Config-driven experiment definition with validated Pydantic schemas and pre-flight scenario validation
- [x] **Phase 3: Concurrent Durable Execution** - Async batch execution with concurrency, retry, resume, and unattended SLO
- [ ] **Phase 4: Scoring, Diagnostics, and Leaderboards** - Pluggable scoring, convergence health detection, ranked leaderboard output
- [ ] **Phase 5: Run Analysis CLI** - Query, compare, and inspect past experiment runs
- [ ] **Phase 6: Extensibility** - Problem-type extensibility via ProblemSpec protocol
- [ ] **Phase 7: Model Packaging** - Export winning runs as self-contained deployable packages

## Phase Details

### Phase 1: Durable Storage Foundation
**Goal**: Every experiment run is durably identified, stored, and observable from the moment it is created -- no data loss on crash, no silent failures, no opaque print statements, and training checkpoints are persisted for downstream packaging
**Depends on**: Nothing (first phase)
**Requirements**: IDENT-01, IDENT-02, IDENT-03, IDENT-04, IDENT-08, CONF-04, CONF-08, RSLT-03, RSLT-04, EXEC-02, EXEC-03, EXEC-05
**Success Criteria** (what must be TRUE):
  1. Researcher runs a batch and each scenario gets a unique ID visible in a structured `artifacts/{batch_run_id}/{scenario_run_id}/` directory on disk
  2. If the process is killed mid-batch (Ctrl-C, OOM, laptop sleep), all completed scenario results are preserved on disk and in the SQLite database
  3. Failed individual scenarios are recorded with error details in the database, not silently dropped from results
  4. All platform output uses structured logging with configurable `--log-level` (DEBUG/INFO/WARNING/ERROR), no print() statements remain
  5. Each run's full config (scenario grid, batch config, git SHA, seed, schema versions) is serialized as a manifest file alongside artifacts
  6. Training checkpoints fetched from the FK backend are durably stored in the scenario artifact directory, ready for downstream model packaging
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md -- Domain models (Pydantic v2) and storage layer (SQLite + filesystem artifacts)
- [x] 01-02-PLAN.md -- CLI migration to Typer and structured logging with structlog
- [x] 01-03-PLAN.md -- Orchestrator integration with incremental writes, manifest generation, and checkpoint fetch

### Phase 2: YAML Manifests, Validation, and Domain Models
**Goal**: Researchers define experiments in version-controlled YAML files with validated schemas, and invalid parameter combinations are caught at pre-flight before any simulation is submitted
**Depends on**: Phase 1
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-05, CONF-06, CONF-07, RSLT-01, RSLT-02
**Success Criteria** (what must be TRUE):
  1. Researcher writes an experiment.yaml specifying scenario grid, batch config, scoring strategy, and output paths, then runs it via `--manifest path/to/experiment.yaml`
  2. Identical manifest files produce the same content hash, and changing any parameter produces a different hash
  3. Manifests support model/architecture sweeps as a first-class axis alongside PDE parameter sweeps
  4. All run results conform to a structured schema with required fields (status, train_loss, grad_norm, runtime_seconds, error_stats, rank_score); malformed results are rejected with clear errors
  5. Manifests with invalid parameter combinations (non-positive-definite correlation matrices, out-of-range volatilities, dimension-incompatible option types) are rejected at pre-flight with clear error messages before any simulation is submitted
**Plans**: 4 plans (3 original + 1 gap closure)

Plans:
- [x] 02-01-PLAN.md -- ExperimentManifest schema, content hashing, and strict result schemas (TDD)
- [x] 02-02-PLAN.md -- Domain-specific pre-flight validation (PSD, ranges, compatibility) (TDD)
- [x] 02-03-PLAN.md -- CLI --manifest option, scenario generation from manifest, orchestrator wiring
- [x] 02-04-PLAN.md -- Gap closure: basket OptionType enum + preflight test validation path

### Phase 3: Concurrent Durable Execution
**Goal**: A 50-200 scenario batch runs concurrently, survives crashes and transient errors, and completes unattended without manual intervention
**Depends on**: Phase 1, Phase 2
**Requirements**: EXEC-01, EXEC-04, EXEC-06, EXEC-07
**Success Criteria** (what must be TRUE):
  1. Batch simulations execute concurrently with a configurable concurrency limit (e.g., 10-20 simultaneous polls), achieving wall-time proportional to (sequential time / concurrency)
  2. If the process crashes mid-batch, researcher can run `resume-batch` and only incomplete scenarios are retried (completed scenarios are never rerun unless `--force` is specified)
  3. Transient backend HTTP errors (timeouts, 5xx) are retried with exponential backoff up to a configurable max, without aborting the batch
  4. A 100-scenario batch achieves >=95% scenario success rate and completes without manual intervention
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md -- Dependencies, schema v2 migration, async HTTP client, and retry configuration
- [x] 03-02-PLAN.md -- Async orchestrator with concurrent execution, retry, fault isolation, and resume
- [x] 03-03-PLAN.md -- CLI wiring for async run-batch and resume-batch commands

### Phase 4: Scoring, Diagnostics, and Leaderboards
**Goal**: Ranking reflects actual convergence quality with pluggable scoring, automated health diagnostics, and leaderboards that surface both rank and convergence health
**Depends on**: Phase 2, Phase 3
**Requirements**: RSLT-05, RSLT-06, RSLT-07, RSLT-08, RSLT-09
**Success Criteria** (what must be TRUE):
  1. Researcher can select from built-in scorers (loss-based, convergence-rate, Pareto multi-objective) or provide a custom scoring function via manifest config
  2. Each scenario result includes an automated convergence health label (healthy, oscillating, stagnating, or exploding) based on loss and gradient patterns
  3. Leaderboard output displays rank score alongside convergence health label for every scenario, enabling the researcher to spot problematic runs at a glance
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Run Analysis CLI
**Goal**: Researchers can query, compare, and drill into past experiment runs from the command line, turning individual batches into a systematic research program
**Depends on**: Phase 1, Phase 4
**Requirements**: IDENT-05, IDENT-06, IDENT-07
**Success Criteria** (what must be TRUE):
  1. Researcher can list all past runs with summary metrics (timestamp, status, scenario count, score summary) via `list-runs`
  2. Researcher can compare two runs side-by-side, aligned by scenario parameters, with delta reporting via `compare-runs`
  3. Researcher can view full detailed results for any past run (per-scenario breakdown, convergence health, config) via `show-run`
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

### Phase 6: Extensibility
**Goal**: New PDE problem types can be added without modifying orchestrator internals, via a clean ProblemSpec protocol
**Depends on**: Phase 2, Phase 4
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-04
**Success Criteria** (what must be TRUE):
  1. A new PDE problem type can be added by implementing the ProblemSpec protocol (parameter schema, scenario generator, scorer, validator) without modifying any orchestrator code
  2. Researcher selects problem type via `problem_id` field in the manifest, and the platform ships with `black_scholes` and `harmonic_oscillator` built-in
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

### Phase 7: Model Packaging
**Goal**: The winning run from any batch can be exported as a self-contained, reproducible model package ready for downstream use
**Depends on**: Phase 1, Phase 4, Phase 5
**Requirements**: PKG-01, PKG-02, PKG-03, PKG-04, PKG-05
**Success Criteria** (what must be TRUE):
  1. Researcher can export the winning run via `export-model` CLI command, producing a self-contained directory
  2. Model package contains checkpoint/weights, exact training config, scenario config, seed, and full environment metadata -- enough to reproduce the training run from scratch
  3. Model package includes a validation summary (final metrics, convergence health, acceptance threshold results) and a manifest describing all contents
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Durable Storage Foundation | 3/3 | Executed (UAT in progress) | 2026-02-19 |
| 2. YAML Manifests, Validation, and Domain Models | 4/4 | Complete (gaps closed) | 2026-02-21 |
| 3. Concurrent Durable Execution | 3/3 | Complete (UAT passed) | 2026-02-22 |
| 4. Scoring, Diagnostics, and Leaderboards | 0/2 | Not started | - |
| 5. Run Analysis CLI | 0/1 | Not started | - |
| 6. Extensibility | 0/2 | Not started | - |
| 7. Model Packaging | 0/1 | Not started | - |

---
*Roadmap created: 2026-02-19*
*Last updated: 2026-02-22 (Phase 3 complete: UAT 7/7 passed, 152 tests, ready for Phase 4)*
