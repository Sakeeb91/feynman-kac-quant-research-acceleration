---
phase: 02-yaml-manifests-validation-and-domain-models
plan: 04
subsystem: validation
tags: [pydantic, enum, basket-options, preflight-validation]

# Dependency graph
requires:
  - phase: 02-yaml-manifests-validation-and-domain-models (plan 02)
    provides: "preflight validation framework with _BASKET_OPTION_TYPES set in constraints.py"
provides:
  - "OptionType enum with basket, basket_call, basket_put members"
  - "End-to-end validation path: YAML basket option -> Pydantic enum coercion -> preflight dim check"
affects: [phase-03-concurrent-execution, experiment-manifests]

# Tech tracking
tech-stack:
  added: []
  patterns: ["model_validate for tests exercising real Pydantic coercion paths"]

key-files:
  created: []
  modified:
    - src/fk_quant_research_accel/models/enums.py
    - tests/test_validation.py

key-decisions:
  - "Keep model_construct for 2 error-aggregation tests that need intentionally Pydantic-invalid data (volatilities=0.0)"
  - "Convert only the 2 basket-specific preflight tests to model_validate (pure basket path validation)"

patterns-established:
  - "Use model_validate in tests when exercising real Pydantic enum coercion is the goal"
  - "Use model_construct in tests when testing preflight aggregation with intentionally invalid schema data"

# Metrics
duration: 2min
completed: 2026-02-21
---

# Phase 02 Plan 04: Basket OptionType Enum Gap Closure Summary

**Extended OptionType enum with basket/basket_call/basket_put so preflight dim-option compatibility check is reachable via real Pydantic validation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-21T18:27:20Z
- **Completed:** 2026-02-21T18:29:07Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added BASKET, BASKET_CALL, BASKET_PUT to OptionType enum, closing the UAT gap from test 6
- Converted 2 basket-specific preflight tests from model_construct to model_validate, proving end-to-end Pydantic coercion works
- Confirmed `validate_dimension_option_compatibility` in constraints.py is no longer dead code for basket options
- All 115 tests pass, lint clean, type checks clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Add basket enum values and update basket preflight tests** - `c54c537` (feat)

**Plan metadata:** `97c4395` (docs: complete plan)

## Files Created/Modified
- `src/fk_quant_research_accel/models/enums.py` - Added BASKET, BASKET_CALL, BASKET_PUT enum members
- `tests/test_validation.py` - Converted 2 basket tests from model_construct to model_validate

## Decisions Made
- **model_construct retained for 2 error-aggregation tests:** `test_preflight_collects_multiple_errors` and `test_preflight_returns_preflight_error_objects` intentionally pass `volatilities=[0.0]` which Pydantic's field_validator rejects. These tests verify preflight error *aggregation* across multiple violation types, not basket enum acceptance. Keeping model_construct is correct because these tests need to bypass schema validation to reach preflight with multiple intentional violations.
- **2 basket-specific tests converted (not 5 as plan estimated):** Only `test_preflight_catches_dim_option_incompatibility` and `test_preflight_checks_cartesian_product_combinations` use basket with otherwise-valid data. These are the tests that directly prove the UAT gap is closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reverted 2 error-aggregation tests back to model_construct**
- **Found during:** Task 1 (test verification)
- **Issue:** Plan specified converting all basket tests to model_validate, but 2 tests (`test_preflight_collects_multiple_errors`, `test_preflight_returns_preflight_error_objects`) intentionally use `volatilities=[0.0]` which Pydantic's `@field_validator("volatilities")` rejects at schema parse time, preventing the grid from being created
- **Fix:** Kept these 2 tests as model_construct (they test preflight error aggregation, not basket enum acceptance); converted only the 2 pure basket-path tests to model_validate
- **Files modified:** tests/test_validation.py
- **Verification:** All 115 tests pass; basket dim-option path confirmed reachable via inline verification script
- **Committed in:** c54c537 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Adjusted test conversion count from plan's estimate to match actual code structure. The objective (basket enum acceptance + preflight reachability) is fully achieved.

## Issues Encountered
None - the deviation was discovered and resolved during standard verification.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 gap closure complete: all UAT scenarios now pass
- OptionType enum covers all option types referenced in preflight constraints
- Ready for Phase 3 concurrent execution work

## Self-Check: PASSED

- [x] src/fk_quant_research_accel/models/enums.py exists
- [x] tests/test_validation.py exists
- [x] 02-04-SUMMARY.md exists
- [x] Commit c54c537 exists in git log
- [x] BASKET, BASKET_CALL, BASKET_PUT enum members present
- [x] model_validate calls present in test file (3 total: 2 basket tests + 1 helper)

---
*Phase: 02-yaml-manifests-validation-and-domain-models*
*Completed: 2026-02-21*
