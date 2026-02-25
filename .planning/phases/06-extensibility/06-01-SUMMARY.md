---
phase: 06-extensibility
plan: 01
subsystem: problems-module-foundation
tags: [tdd, extensibility, protocol, registry]
requires:
  - phase: 02-yaml-manifests-validation-and-domain-models
    provides: ExperimentManifest and scenario grid schemas
  - phase: 04-scoring-diagnostics-leaderboards
    provides: Scoring strategy contract
provides:
  - ProblemSpec protocol contract and BaseProblemSpec defaults
  - Dict-backed problem registry with lazy built-in registration
  - Built-in specs for black_scholes and harmonic_oscillator
  - Full tests for protocol, registry, and built-ins
affects: [problems, tests]
completed: 2026-02-25
---

# Phase 6 Plan 01 Summary

Implemented the extensibility foundation as a self-contained `problems/` module.

## Delivered
- Added protocol + base defaults:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/problems/protocol.py`
  - `ProblemParams` base model
  - runtime-checkable `ProblemSpec` protocol with required members
  - `BaseProblemSpec` defaults for `validate`, `default_scorer`,
    `default_pareto_objectives`, and `supports_scoring_strategy`

- Added registry:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/problems/registry.py`
  - `_PROBLEM_REGISTRY` map
  - `register_problem`, `get_problem_spec`, `list_problem_ids`
  - lazy built-in registration + nearest-match suggestions for unknown IDs

- Added built-in specs:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/problems/black_scholes.py`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/problems/harmonic_oscillator.py`
  - both register at module import and are discoverable through registry APIs

- Added package exports:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/problems/__init__.py`

- Added complete test coverage:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_problems.py`

## Verification
- `python3 -m pytest tests/test_problems.py -q` -> `33 passed`
- `python3 -m pytest tests/ -q` -> `304 passed`
- `python3 -c "from fk_quant_research_accel.problems import ProblemSpec, BaseProblemSpec, get_problem_spec, register_problem, list_problem_ids"` -> passed
- `python3 -c "from fk_quant_research_accel.problems import get_problem_spec; bs = get_problem_spec('black_scholes'); ho = get_problem_spec('harmonic_oscillator'); print(bs.problem_id, ho.problem_id)"` -> `black_scholes harmonic_oscillator`
- `python3 -c "from fk_quant_research_accel.problems import get_problem_spec; spec = get_problem_spec('black_scholes'); scenarios = spec.generate_scenarios({'dimensions': [2], 'volatilities': [0.2], 'correlations': [0.3], 'option_types': ['call']}, [{'architecture': 'default'}]); print(len(scenarios), scenarios[0])"` -> `1` scenario with expected fields

## Outcome
Plan `06-01` is complete. The codebase now has a reusable problem-spec abstraction, built-in Black-Scholes and harmonic-oscillator specs, a discoverable registry API with user-friendly lookup errors, and TDD coverage for the full contract.
