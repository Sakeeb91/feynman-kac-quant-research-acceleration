---
phase: 02-yaml-manifests-validation-and-domain-models
plan: 03
subsystem: cli
tags: [typer, pydantic, manifest, preflight, orchestrator, tdd]
requires:
  - phase: 02-yaml-manifests-validation-and-domain-models
    provides: manifest schema, hashing, strict result models, and preflight validation primitives
provides:
  - CLI `run-batch --manifest` integration with load, hash, validate, and execute pipeline
  - Manifest-driven scenario Cartesian expansion including model sweep axes
  - Batch artifact manifest persistence of source manifest hash
affects: [phase-03-concurrency, cli, orchestrator, manifest-workflow]
tech-stack:
  added: []
  patterns: [manifest-overrides-flags CLI flow, structured preflight failure logging, model-sweep Cartesian scenario generation]
key-files:
  created: []
  modified:
    - src/fk_quant_research_accel/orchestrator.py
    - src/fk_quant_research_accel/cli.py
    - src/fk_quant_research_accel/models/manifest.py
    - src/fk_quant_research_accel/__init__.py
    - tests/test_cli.py
    - tests/test_orchestrator.py
key-decisions:
  - "Treat --manifest as the authoritative config source and require --base-url only for legacy flag-based runs."
  - "Persist experiment_manifest_hash in run artifacts via RunManifest for deterministic config traceability."
  - "Keep Scenario backward compatible by making model_config optional and additive."
patterns-established:
  - "Manifest run pipeline: load_manifest -> content_hash -> validate_manifest -> generate_scenarios_from_manifest -> run_batch."
  - "Model sweep axis validation enforces index-aligned lengths for hidden_sizes/activations/optimizers."
duration: 9 min
completed: 2026-02-20
---

# Phase 2 Plan 3: Manifest CLI and Orchestrator Wiring Summary

**Researchers can now execute YAML-defined experiments through `run-batch --manifest`, with preflight gating, deterministic hashing, and manifest-driven scenario/model sweep expansion.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-20T17:08:05Z
- **Completed:** 2026-02-20T17:17:21Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Added `generate_scenarios_from_manifest()` with full Cartesian expansion over PDE grid and model sweep axes.
- Extended `Scenario` with optional `model_config` and preserved backward compatibility for existing scenario construction.
- Added `--manifest` execution path in CLI: manifest load, content hash logging, preflight validation, scenario generation, and run execution.
- Kept legacy `--base-url` flag path working and enforced explicit base-url only when manifest is absent.
- Added artifact-level provenance by persisting `experiment_manifest_hash` into the batch run manifest.
- Expanded test coverage across CLI/orchestrator integrations and edge cases (115 total tests now passing).

## Task Commits

Each task was committed atomically:

1. **Task 1: Manifest scenario generation and orchestrator updates**  
   `f3bba65` .. `aafc6a7`
2. **Task 2: CLI manifest integration and compatibility path**  
   `495825c` .. `31906dd`

## Files Created/Modified
- `src/fk_quant_research_accel/orchestrator.py` - Manifest scenario generator, scenario model sweep support, manifest hash propagation.
- `src/fk_quant_research_accel/cli.py` - `--manifest` flow, preflight failure handling, hash logging, backward-compatible legacy branch.
- `src/fk_quant_research_accel/models/manifest.py` - Optional `experiment_manifest_hash` in `RunManifest`.
- `src/fk_quant_research_accel/__init__.py` - Exported `generate_scenarios_from_manifest`.
- `tests/test_orchestrator.py` - Manifest scenario generation + hash persistence + compatibility tests.
- `tests/test_cli.py` - Manifest option help/path/failure/override behavior tests.

## Decisions Made
- Kept CLI backward compatibility by preserving existing flags while introducing manifest-first execution semantics.
- Enforced model sweep index alignment inside orchestrator to prevent silent mispairing across architecture and optimizer/activation axes.
- Logged preflight errors one-by-one to support full batch diagnostics before any backend submission.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Scenario failure-preservation test assumed directory ordering**
- **Found during:** Task 1 verification (`tests/test_orchestrator.py`)
- **Issue:** UUID-based scenario directory names made lexicographic order non-deterministic, causing flaky status assertions.
- **Fix:** Updated assertion to check observed status set equals `{\"completed\", \"failed\"}`.
- **Files modified:** `tests/test_orchestrator.py`
- **Verification:** `pytest tests/test_orchestrator.py -v`
- **Committed in:** `54237c8`

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Improved deterministic test behavior without scope change.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Ready for Phase 3 concurrency work with manifest-driven input and preflight validation integrated.
- CLI and orchestrator now expose the full manifest pipeline needed for unattended multi-scenario execution.

---
*Phase: 02-yaml-manifests-validation-and-domain-models*
*Completed: 2026-02-20*
