---
phase: 06-extensibility
plan: 02
subsystem: pipeline-integration
tags: [execute, extensibility, orchestration, validation, storage]
requires:
  - phase: 06-extensibility
    plan: 01
    provides: ProblemSpec protocol and registry
provides:
  - ProblemSpec-aware dispatch in sync and async orchestrators
  - Batch metadata persistence of problem_id (schema v4)
  - Resume path recovery of persisted problem_id
  - Manifest preflight problem resolution and strategy compatibility checks
  - Problem-agnostic run comparison scenario alignment key
  - CLI manifest routing through ProblemSpec with deprecation warning for implicit defaults
affects: [store, orchestrator, async_orchestrator, validation, cli, run_analysis, tests]
completed: 2026-02-25
---

# Phase 6 Plan 02 Summary

Integrated ProblemSpec across execution, validation, storage, and CLI layers.

## Delivered
- Storage and schema:
  - Added SQLite schema v4 migration with `batch_runs.problem_id` defaulting to `black_scholes`.
  - Updated `MetadataStore.create_batch_run()` to persist explicit `problem_id` while preserving backward-compatible defaults.

- Orchestrator dispatch:
  - Added `problem_id` threading in both sync `run_batch()` and async `run_batch_async()` paths.
  - Removed hardcoded submission IDs and routed simulation creation using the selected problem.
  - Added scorer precedence resolver in sync/async orchestrators:
    - `custom_scorer` override
    - otherwise selected `ScoringConfig.strategy` if supported by the problem
    - otherwise ProblemSpec `default_scorer`

- Resume behavior:
  - `resume_batch_async()` now reads `problem_id` from persisted `batch_runs` metadata (with safe default fallback) and reuses it for resumed submissions.
  - Scenario rehydration now uses `Scenario.from_parameters()` to preserve extra problem-specific fields.

- Manifest preflight:
  - Preflight now resolves `manifest.problem_id` via registry and returns a targeted `problem_id` error for invalid values.
  - Added strategy compatibility check via `problem_spec.supports_scoring_strategy()`.
  - Added delegated scenario validation through `problem_spec.generate_scenarios(...); problem_spec.validate(...)`.

- CLI manifest routing:
  - Manifest `run-batch` now resolves `problem_spec = get_problem_spec(experiment.problem_id)`.
  - Scenario generation for manifest mode now routes through `problem_spec.generate_scenarios(...)` and converts payloads via `Scenario.from_parameters()`.
  - Added deprecation warning log when manifest omits `problem_id` and implicitly defaults to `black_scholes`.
  - CLI now passes selected `problem_id` into async execution.

- Run analysis:
  - Comparison alignment key now normalizes the full `scenario_json` payload with sorted JSON, making matching problem-agnostic and robust to key order.

## Verification
- `python3 -m pytest tests/test_store.py -q`
- `python3 -m pytest tests/test_validation.py -q`
- `python3 -m pytest tests/test_run_analysis.py -q`
- `python3 -m pytest tests/test_orchestrator.py -q`
- `python3 -m pytest tests/test_async_orchestrator.py -q`
- `python3 -m pytest tests/test_cli.py -q`
- `python3 -m pytest tests/ -q`

## Outcome
Plan `06-02` is complete. The execution pipeline now treats `problem_id` as first-class metadata and behavior, enabling extensible problem dispatch without hardcoded orchestrator internals while keeping backward compatibility intact.
