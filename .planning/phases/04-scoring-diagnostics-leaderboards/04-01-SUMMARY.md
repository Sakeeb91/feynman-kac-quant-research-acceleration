---
phase: 04-scoring-diagnostics-leaderboards
plan: 01
subsystem: scoring-and-diagnostics
tags: [tdd, scoring, pareto, diagnostics, validation]
requires:
  - phase: 02-yaml-manifests-validation-and-domain-models
    provides: ExperimentManifest and ScoringConfig schemas
  - phase: 03-concurrent-durable-execution
    provides: baseline reporting and validation integration points
provides:
  - Pluggable scorer registry with built-in and custom scorer support
  - Pareto non-dominated sorting and rank score assignment
  - Convergence health diagnostics using final-state and history heuristics
  - Backward-compatible `compute_score()` delegation to configured scorer
  - Preflight validation for custom scorer dotted paths
affects: [models, scoring, diagnostics, reporting, validation, tests]
tech-stack:
  added: []
  patterns: [registry decorator dispatch, post-hoc Pareto ranking, heuristic health classification]
key-files:
  created:
    - .planning/phases/04-scoring-diagnostics-leaderboards/04-01-SUMMARY.md
    - src/fk_quant_research_accel/scoring/__init__.py
    - src/fk_quant_research_accel/scoring/registry.py
    - src/fk_quant_research_accel/scoring/scorers.py
    - src/fk_quant_research_accel/scoring/pareto.py
    - src/fk_quant_research_accel/diagnostics/__init__.py
    - src/fk_quant_research_accel/diagnostics/health.py
    - tests/test_scoring.py
    - tests/test_diagnostics.py
  modified:
    - src/fk_quant_research_accel/models/enums.py
    - src/fk_quant_research_accel/models/experiment.py
    - src/fk_quant_research_accel/models/result.py
    - src/fk_quant_research_accel/models/__init__.py
    - src/fk_quant_research_accel/reporting.py
    - src/fk_quant_research_accel/validation/preflight.py
    - tests/test_reporting.py
    - tests/test_validation.py
key-decisions:
  - "Keep `compute_score(record)` backward-compatible by defaulting to `ScoringConfig()` and delegating through `get_scorer`."
  - "Treat invalid/missing Pareto objective values as last-front records via non-dominated sort invalid bucket."
  - "Classify failed and numerically unstable runs as `ConvergenceHealth.EXPLODING` before any other heuristic."
  - "Validate custom scorer imports at preflight using the same dotted-path loader as runtime dispatch."
patterns-established:
  - "Scoring strategy selection is centralized through `get_scorer(config)` with explicit custom override precedence."
  - "Convergence diagnostics prefer richer `loss_history` signals when available, otherwise fall back to final-state heuristics."
completed: 2026-02-22
---

# Phase 4 Plan 01 Summary

Implemented the Phase 4 scoring + diagnostics foundation with full TDD coverage.

## Delivered
- Added schema extensions:
  - `ConvergenceHealth` enum in `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/models/enums.py`
  - `ScoringConfig.custom_scorer` and `ScoringConfig.pareto_objectives` in `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/models/experiment.py`
  - `CompletedScenarioResult.convergence_health` in `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/models/result.py`
  - `ConvergenceHealth` export from `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/models/__init__.py`

- Added pluggable scoring module:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/scoring/registry.py`
    - `ScorerFn`, `register_scorer`, `get_scorer`, `_import_custom_scorer`
    - `LOSS_BASED` strategy closure captures `grad_norm_weight`
    - custom scorer dotted-path import with callable validation
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/scoring/scorers.py`
    - `score_loss_based`
    - `score_convergence_rate`
    - `score_pareto_placeholder`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/scoring/pareto.py`
    - `dominates`
    - `non_dominated_sort`
    - `assign_pareto_scores`

- Added convergence diagnostics module:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/diagnostics/health.py`
    - finite checks and exploding safeguards
    - history-based classification (`loss_history`, optional `grad_norm_history`)
    - final-state fallback classification for healthy/oscillating/stagnating/exploding

- Migrated score API:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/reporting.py`
    - `compute_score(record, scoring_config=None)` now delegates through scorer registry
    - default behavior remains loss-based + `grad_norm_weight=0.01`

- Added custom scorer preflight validation:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/validation/preflight.py`
    - validates `scoring.custom_scorer` dotted path importability and callable contract
    - emits `PreflightError(field="scoring.custom_scorer", ...)` on failure

- Added/updated tests:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_scoring.py`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_diagnostics.py`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_reporting.py`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_validation.py`

## Verification
- `python3 -m pytest tests/test_scoring.py -q` -> passed
- `python3 -m pytest tests/test_diagnostics.py -q` -> passed
- `python3 -m pytest tests/test_reporting.py -q` -> passed
- `python3 -m pytest tests/test_validation.py -q` -> passed
- `python3 -m pytest tests/ -q` -> `191 passed`
- `python3 -c "from fk_quant_research_accel.scoring import get_scorer, assign_pareto_scores"` -> passed
- `python3 -c "from fk_quant_research_accel.diagnostics import diagnose_convergence; from fk_quant_research_accel.models import ConvergenceHealth"` -> passed
- `python3 -c "from fk_quant_research_accel.reporting import compute_score; print(compute_score({'status': 'completed', 'train_loss': 0.05, 'grad_norm': 1.0}))"` -> `0.060000000000000005`

## Outcome
Plan 04-01 is complete: scoring is now pluggable and extensible, Pareto ranking is available, convergence health diagnostics are implemented, `compute_score` remains backward-compatible, and invalid custom scorer references are caught before execution.
