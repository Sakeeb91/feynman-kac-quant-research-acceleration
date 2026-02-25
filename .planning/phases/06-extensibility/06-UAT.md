---
status: complete
phase: 06-extensibility
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md]
started: 2026-02-25T12:00:00Z
updated: 2026-02-25T12:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Built-in problem types discoverable
expected: `list_problem_ids()` returns `['black_scholes', 'harmonic_oscillator']` and both are retrievable via `get_problem_spec()`
result: pass
evidence: `list_problem_ids()` returned `['black_scholes', 'harmonic_oscillator']`

### 2. Registry error with nearest-match suggestion
expected: `get_problem_spec("black_shoals")` raises ValueError with message listing valid IDs and suggesting "Did you mean 'black_scholes'?"
result: pass
evidence: `Unknown problem_id: 'black_shoals'. Valid IDs: black_scholes, harmonic_oscillator. Did you mean 'black_scholes'?`

### 3. BlackScholesSpec scenario generation
expected: `generate_scenarios({'dimensions': [2, 5], 'volatilities': [0.2], 'correlations': [0.3], 'option_types': ['call']}, [model_config])` produces 2 scenarios with correct fields (dim, volatility, correlation, option_type, model_config)
result: pass
evidence: 2 scenarios with fields `dim`, `volatility`, `correlation`, `option_type`, `model_config`

### 4. HarmonicOscillatorSpec scenario generation
expected: `generate_scenarios({'dimensions': [1, 2], 'omegas': [0.5, 1.0], 'masses': [1.0], 'potential_types': ['quadratic']}, [model_config])` produces 4 scenarios (2x2x1x1) with fields dim, omega, mass, potential_type, model_config
result: pass
evidence: 4 scenarios with fields `dim`, `omega`, `mass`, `potential_type`, `model_config`

### 5. ProblemSpec protocol conformance and defaults
expected: `isinstance(spec, ProblemSpec)` is True. `default_scorer` returns `train_loss` for completed records, `inf` for failed. `default_pareto_objectives` returns `['train_loss', 'grad_norm']`. `supports_scoring_strategy` returns True.
result: pass
evidence: isinstance=True, scorer(completed)=0.05, scorer(failed)=inf, pareto=['train_loss', 'grad_norm'], supports=True

### 6. Preflight catches invalid problem_id
expected: Manifest with `problem_id="nonexistent_problem"` produces a PreflightError on field `problem_id` listing valid IDs
result: pass
evidence: 1 error: `field=problem_id, message=Unknown problem_id: 'nonexistent_problem'. Valid IDs: black_scholes, harmonic_oscillator.`

### 7. No hardcoded problem_id in orchestrators
expected: `rg 'problem_id="black_scholes"' orchestrator.py async_orchestrator.py` returns zero matches -- all submission paths now use ProblemSpec dispatch
result: pass
evidence: zero matches returned

### 8. Schema v4 migration adds problem_id column
expected: `CURRENT_SCHEMA_VERSION` is 4. `batch_runs` table has `problem_id` column. New databases created via `init_db` include the column.
result: pass
evidence: schema version=4, `problem_id` present in batch_runs columns

### 9. Deprecation detection for missing problem_id
expected: Manifest without explicit `problem_id` defaults to `"black_scholes"` and `"problem_id" not in manifest.model_fields_set` is True (enabling deprecation warning). Manifest WITH explicit `problem_id` has it in `model_fields_set`.
result: pass
evidence: `problem_id=black_scholes`, `problem_id in model_fields_set=False`

### 10. Backward compatibility and full test suite
expected: `Scenario`, `generate_black_scholes_scenarios`, `generate_scenarios_from_manifest` are still importable from `orchestrator.py`. Full test suite passes (323 tests, 0 failures).
result: pass
evidence: backward-compat imports OK, `323 passed in 4.06s`

## Summary

total: 10
passed: 10
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
