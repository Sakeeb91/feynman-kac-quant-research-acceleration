---
status: diagnosed
phase: 02-yaml-manifests-validation-and-domain-models
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md]
started: 2026-02-21T12:00:00Z
updated: 2026-02-21T12:12:00Z
---

## Current Test

[testing complete]

## Tests

### 1. CLI --manifest option visible in help
expected: Running `.venv/bin/python -m fk_quant_research_accel.cli run-batch --help` shows a `--manifest` option described as accepting a path to an experiment YAML manifest.
result: pass

### 2. Valid manifest loads and passes preflight
expected: Create a minimal `experiment.yaml` with valid params, run `.venv/bin/python -m fk_quant_research_accel.cli run-batch --manifest experiment.yaml`. It should pass manifest loading and preflight validation (it will fail at backend connection, but the manifest hash and "preflight passed" log lines should appear before the connection error).
result: pass

### 3. Content hash is deterministic
expected: Loading the same experiment.yaml twice produces the same SHA-256 content hash. Running `.venv/bin/python -c "from fk_quant_research_accel.models import load_manifest; from fk_quant_research_accel.models.hashing import content_hash; m = load_manifest('experiment.yaml'); print(content_hash(m)); print(content_hash(m))"` prints two identical hash strings.
result: pass

### 4. Invalid volatility rejected at preflight
expected: Create an experiment.yaml with `volatilities: [0.0]` (zero is invalid). Running with `--manifest` exits with code 1 and prints a clear error message about volatility being out of range before any backend submission.
result: pass

### 5. Non-PSD correlation matrix rejected at preflight
expected: Create an experiment.yaml with a non-positive-definite correlation matrix (e.g., `correlations: [[1.0, 0.99, 0.99], [0.99, 1.0, -0.99], [0.99, -0.99, 1.0]]`). Running with `--manifest` exits with code 1 and prints a clear error about the matrix not being positive semi-definite.
result: pass

### 6. Dimension-option incompatibility rejected
expected: Create an experiment.yaml with `dimensions: [1]` and `option_types: [basket]`. Running with `--manifest` exits with code 1 and prints an error about basket options requiring dimension >= 2.
result: issue
reported: "this currently fails earlier at manifest schema validation, not preflight. option_types: [basket] is rejected by ExperimentManifest enum validation (OptionType), so you get manifest_load_failed. Exit code is correctly 1, but the expected preflight message (basket options require dim >= 2) is never reached because basket is not an allowed option type in the schema."
severity: minor

### 7. Model sweep generates correct scenario count
expected: Running `.venv/bin/python -c "from fk_quant_research_accel.models import ExperimentManifest; from fk_quant_research_accel.orchestrator import generate_scenarios_from_manifest; m = ExperimentManifest.model_validate({'backend_url': 'http://localhost:8000', 'scenario_grid': {'dimensions': [5, 10], 'volatilities': [0.2, 0.3], 'correlations': [0.0]}, 'model_sweep': {'architectures': ['fnn_3x64', 'resnet_3x64']}}); print(len(generate_scenarios_from_manifest(m)))"` prints `8` (2 dims x 2 vols x 1 corr x 1 option x 2 architectures).
result: pass

### 8. Strict result schema enforces required fields
expected: Running `.venv/bin/python -c "from fk_quant_research_accel.models.result import validate_and_build_result; validate_and_build_result({'status': 'completed', 'scenario_run_id': 'x', 'batch_run_id': 'y', 'simulation_id': 'z', 'scenario_params': {}})"` raises a ValidationError listing missing required fields (train_loss, grad_norm, runtime_seconds, rank_score).
result: pass

### 9. Full test suite passes
expected: Running `.venv/bin/python -m pytest tests/ -v` shows all 115 tests passing with no failures or errors.
result: pass

## Summary

total: 9
passed: 8
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Dimension-option incompatibility (basket with dim=1) is caught at preflight with a clear message about dimension requirement"
  status: failed
  reason: "User reported: basket is not in OptionType enum, so manifest schema validation rejects it before preflight can check dim-option compatibility. The preflight basket check is unreachable dead code."
  severity: minor
  test: 6
  root_cause: "_BASKET_OPTION_TYPES = {'basket', 'basket_call', 'basket_put'} in constraints.py references strings not present in OptionType enum (call, put, asian_call, barrier_up_and_out). ScenarioGridConfig.option_types is typed list[OptionType], so Pydantic rejects basket before preflight runs. Tests pass only because they use model_construct() which bypasses validation."
  artifacts:
    - path: "src/fk_quant_research_accel/models/enums.py"
      issue: "OptionType enum missing basket, basket_call, basket_put values"
    - path: "src/fk_quant_research_accel/validation/constraints.py"
      issue: "_BASKET_OPTION_TYPES references strings not in OptionType enum"
    - path: "tests/test_validation.py"
      issue: "5 basket tests use model_construct() to bypass Pydantic, masking the dead code"
  missing:
    - "Add basket, basket_call, basket_put to OptionType enum OR remove dead basket check from constraints.py"
  debug_session: ""
