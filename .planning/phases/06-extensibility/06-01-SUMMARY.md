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
