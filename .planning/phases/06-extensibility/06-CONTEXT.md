# Phase 6: Extensibility - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Problem-type extensibility via a ProblemSpec protocol. New PDE problem types can be added without modifying orchestrator internals. Platform ships with `black_scholes` and `harmonic_oscillator` built-in. Researcher selects problem type via `problem_id` in the manifest.

Requirements: EXT-01, EXT-02, EXT-03, EXT-04.

</domain>

<decisions>
## Implementation Decisions

### Protocol contract
- Strict core ProblemSpec contract with defaults for convenience
- Required members: `problem_id`, parameter schema (Pydantic model), scenario generator, validator, scorer entrypoint
- Flexible: scorer and validator can use default implementations so new specs can start minimal without breaking the contract
- A new ProblemSpec that only provides `problem_id`, parameter schema, and scenario generator should still be valid (defaults fill scorer/validator)

### Scorer interaction
- Clear precedence chain to avoid Phase 4 / Phase 6 conflicts:
  - `custom_scorer` (manifest-level) > `ScoringConfig.strategy` (global) > ProblemSpec default scorer
- ProblemSpec can reject unsupported scoring strategies during validation (e.g., a problem type that doesn't support Pareto)
- ProblemSpec can provide problem-specific default Pareto objectives

### Built-in migration
- Refactor existing code, don't rewrite from scratch
- First: wrap existing Black-Scholes logic as `BlackScholesSpec` — generator, validator, scorer behavior unchanged
- Second: add `HarmonicOscillatorSpec` as a new implementation
- Then: remove hardcoded `"black_scholes"` submission paths; route through `problem_id` from selected spec
- Persist `problem_id` in run metadata so resume and analysis are unambiguous

### Manifest experience
- Explicit registration (deterministic, testable) — no auto-discovery / plugin scanning
- Manifest selects `problem_id` and has a problem-specific config section (e.g., `problem:` key)
- Errors for missing/invalid `problem_id` should list valid IDs and offer a nearest-match suggestion
- Backward compatibility: default to `black_scholes` when `problem_id` is omitted, but log a deprecation warning

### Claude's Discretion
- Exact ProblemSpec protocol shape (Protocol class vs ABC vs dataclass with methods)
- Registration mechanism internals (dict registry, decorator, or class-based)
- How default scorer/validator implementations are structured
- HarmonicOscillatorSpec parameter ranges and scenario generation details
- Deprecation warning format and log level

</decisions>

<specifics>
## Specific Ideas

- Scorer precedence was deliberate: manifest custom_scorer always wins, then global strategy, then problem default — this preserves Phase 4's pluggable scoring while allowing problem types to define sensible defaults
- The refactor-not-rewrite approach for BlackScholesSpec ensures existing test coverage carries forward
- Persisting `problem_id` in metadata is critical for resume-batch (must know which spec to route to) and for run analysis (compare-runs needs to know problem type)
- Backward compatibility with deprecation warning eases the transition — existing manifests without `problem_id` keep working but researchers are nudged to add it

</specifics>

<deferred>
## Deferred Ideas

- Auto-discovery / plugin scanning for third-party ProblemSpecs — keep it explicit for v1
- Problem-specific visualization or reporting hooks — future enhancement
- Problem-specific CLI subcommands — out of scope

</deferred>

---

*Phase: 06-extensibility*
*Context gathered: 2026-02-25*
