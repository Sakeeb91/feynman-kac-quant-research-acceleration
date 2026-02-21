---
phase: 02-yaml-manifests-validation-and-domain-models
verified: 2026-02-21T18:32:33Z
status: passed
score: 3/3 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 8/9 UAT tests (gap closure re-verification)
  gaps_closed:
    - "OptionType enum extended with basket, basket_call, basket_put so basket option_types pass Pydantic validation and reach preflight dim-check"
    - "5 basket-related preflight tests updated: 2 converted to model_validate (pure basket path), 3 intentionally retained as model_construct (test schema bypass for error aggregation)"
    - "validate_dimension_option_compatibility in constraints.py is now reachable code when basket option is provided via normal manifest loading"
  gaps_remaining: []
  regressions: []
---

# Phase 2: YAML Manifests, Validation, and Domain Models — Verification Report

**Phase Goal:** Researchers define experiments in version-controlled YAML files with validated schemas, and invalid parameter combinations are caught at pre-flight before any simulation is submitted

**Verified:** 2026-02-21T18:32:33Z
**Status:** passed
**Re-verification:** Yes — gap closure after UAT test 6 diagnosis

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | An experiment.yaml with `option_types: [basket]` and `dimensions: [1]` is accepted by Pydantic schema validation and then rejected at preflight with a message about basket options requiring dim >= 2 | VERIFIED | CLI output: `manifest_loaded` event fires (hash printed), then `preflight_validation_failed` with "Option type 'basket' requires dim >= 2, got dim=1." — exit code 1 |
| 2 | The 2 basket-specific preflight tests pass using `model_validate()` (real Pydantic validation), not `model_construct()` (validation bypass) | VERIFIED | `test_preflight_catches_dim_option_incompatibility` (line 314) and `test_preflight_checks_cartesian_product_combinations` (line 342) both use `ScenarioGridConfig.model_validate({...})` with `option_types: ["basket"]` — confirmed in source |
| 3 | All 115 existing tests continue to pass | VERIFIED | `pytest tests/ -v` → 115 passed in 0.54s, 0 failures, 0 errors |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/fk_quant_research_accel/models/enums.py` | OptionType enum with `basket`, `basket_call`, `basket_put` values | VERIFIED | Lines 29-31: `BASKET = "basket"`, `BASKET_CALL = "basket_call"`, `BASKET_PUT = "basket_put"` present immediately after `BARRIER_UP_AND_OUT` |
| `tests/test_validation.py` | Basket preflight tests using `model_validate` instead of `model_construct` | VERIFIED | `test_preflight_catches_dim_option_incompatibility` (line 314) and `test_preflight_checks_cartesian_product_combinations` (line 342) use `model_validate`; error-aggregation tests (`test_preflight_collects_multiple_errors`, `test_preflight_returns_preflight_error_objects`) correctly retain `model_construct` to bypass Pydantic with intentionally invalid volatilities |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/fk_quant_research_accel/validation/constraints.py` | `src/fk_quant_research_accel/models/enums.py` | `_BASKET_OPTION_TYPES` set references `{"basket", "basket_call", "basket_put"}` which now match OptionType enum values | WIRED | `_BASKET_OPTION_TYPES = {"basket", "basket_call", "basket_put"}` in constraints.py line 15; enum values `"basket"`, `"basket_call"`, `"basket_put"` in enums.py lines 29-31 — strings match exactly |
| `tests/test_validation.py` | `src/fk_quant_research_accel/models/experiment.py` | `ScenarioGridConfig.model_validate()` exercises real Pydantic field validation | WIRED | `model_validate` appears at lines 314, 342 in basket preflight tests; confirmed via grep |

### Requirements Coverage

Phase 2 success criterion 5 from ROADMAP.md:

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Manifests with invalid parameter combinations (dimension-incompatible option types) are rejected at pre-flight with clear error messages before any simulation is submitted | SATISFIED | CLI run with `option_types: [basket]` + `dimensions: [1]` produces `preflight_validation_failed` event with message "Option type 'basket' requires dim >= 2, got dim=1." before any backend connection attempt |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_validation.py` | 251, 265, 283, 300, 328, 357, 371 | `model_construct` calls | Info | Intentional — these tests either (a) need to bypass Pydantic with invalid schema data to test preflight error aggregation, or (b) test non-basket paths where bypass is harmless. Not a stub or dead path. |

No blocker anti-patterns found.

### Human Verification Required

None. All three observable truths verified programmatically:

1. CLI invocation with basket+dim=1 manifest confirmed to produce preflight rejection (not schema rejection) with correct error message and exit code 1.
2. Source inspection confirmed `model_validate` usage at exact lines in test file.
3. Full test suite run confirmed 115/115 pass.

### Gaps Summary

No gaps remain. The previously identified gap is closed:

**Closed gap:** `OptionType` enum was missing `basket`, `basket_call`, `basket_put`. This caused `ScenarioGridConfig.option_types` to reject basket strings at Pydantic parse time (before preflight), making `validate_dimension_option_compatibility` in `constraints.py` unreachable dead code for basket options. Tests only passed because they used `model_construct()` to bypass validation.

**Fix applied (commit c54c537):**
- Added 3 enum members to `src/fk_quant_research_accel/models/enums.py`
- Converted 2 pure-basket-path tests to `model_validate()` (proving real end-to-end validation works)
- Retained `model_construct()` in 2 error-aggregation tests that intentionally use `volatilities=[0.0]` to test multi-error preflight collection

**Deviation from plan:** Plan estimated 5 tests to convert; actual was 2. The other 3 retain `model_construct` because they pass `volatilities=[0.0]` which Pydantic's `@field_validator` rejects before preflight can run — keeping `model_construct` is the correct design for those tests.

---

_Verified: 2026-02-21T18:32:33Z_
_Verifier: Claude (gsd-verifier)_
