---
phase: 02-yaml-manifests-validation-and-domain-models
plan: 02
subsystem: validation
tags: [pydantic, validation, preflight, cholesky, tdd]
requires:
  - phase: 02-yaml-manifests-validation-and-domain-models
    provides: ExperimentManifest schema hierarchy from 02-01 for preflight input
provides:
  - Pure constraint validators for PSD, correlation, volatility, scalar-correlation, and dim-option checks
  - Preflight manifest orchestrator with structured PreflightError objects
  - Cross-scenario Cartesian product validation for dimension-option compatibility and matrix-dimension checks
affects: [phase-02-plan-03, cli, orchestrator, concurrent-execution-readiness]
tech-stack:
  added: []
  patterns: [pure-python cholesky validation, structured preflight error aggregation, all-errors reporting]
key-files:
  created:
    - src/fk_quant_research_accel/validation/constraints.py
    - src/fk_quant_research_accel/validation/preflight.py
    - tests/test_validation.py
  modified:
    - src/fk_quant_research_accel/validation/__init__.py
key-decisions:
  - "Use pure-Python Cholesky PSD checks to avoid adding numpy dependency."
  - "Keep unknown option types as pass-through (non-error) while enforcing basket dim >= 2."
  - "Return PreflightError(field, value, message) for every violation and collect all errors in one pass."
patterns-established:
  - "Constraint functions return list[str] for composable validator orchestration."
  - "validate_manifest separates axis checks from Cartesian cross-scenario checks."
duration: 6 min
completed: 2026-02-20
---

# Phase 2 Plan 2: Domain-Specific Preflight Validation Summary

**Preflight validation now blocks invalid experiment manifests with structured, multi-error reporting before any scenario submission.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-20T16:58:02Z
- **Completed:** 2026-02-20T17:04:38Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Implemented pure constraint validators: PSD via Cholesky, matrix shape/range/diagonal checks, volatility bounds, scalar-correlation bounds, and dimension-option compatibility.
- Implemented `validate_manifest()` preflight orchestration with structured `PreflightError` objects.
- Added cross-scenario Cartesian product checks and verified all errors are aggregated (not short-circuited).
- Added complete TDD coverage for constraints and preflight behavior in `tests/test_validation.py` (36 passing tests).

## Task Commits

Each task was committed atomically:

1. **Task 1: Pure constraint validators**  
   `f81f65f` .. `c5759e7` (tests + feat + refactor)
2. **Task 2: Pre-flight validation orchestrator**  
   `d049f05` .. `b232371` (tests + feat + refactor)

## Files Created/Modified
- `src/fk_quant_research_accel/validation/constraints.py` - Constraint primitives and error-message generation.
- `src/fk_quant_research_accel/validation/preflight.py` - Preflight error model and manifest orchestration logic.
- `src/fk_quant_research_accel/validation/__init__.py` - Public exports for validation package.
- `tests/test_validation.py` - End-to-end TDD suite for constraints and preflight orchestration.

## Decisions Made
- Chose Cholesky-based PSD checking in pure Python for deterministic, dependency-free validation.
- Treated unknown option types as non-blocking so backend-specific extensions can pass through.
- Enforced structured preflight failures (`field`, `value`, `message`) to support CLI-friendly reporting in next plan.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Ready for `02-03-PLAN.md` to wire `--manifest` CLI flow and orchestrator integration.
- Preflight validator is now available as a standalone import for CLI and orchestration paths.

---
*Phase: 02-yaml-manifests-validation-and-domain-models*
*Completed: 2026-02-20*
