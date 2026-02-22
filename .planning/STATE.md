# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-19)

**Core value:** A researcher can define a 50-200 scenario batch, walk away, and come back to a ranked leaderboard with full reproducibility metadata and a deployable model package for the winner.
**Current focus:** Phase 3 fully complete (UAT passed, 0 issues); ready to begin Phase 4 planning

## Current Position

Phase: 3 of 7 (Concurrent Durable Execution)
Plan: 3 of 3 in current phase
Status: Complete (UAT passed: 7/7, 0 issues)
Last activity: 2026-02-22 -- Phase 3 UAT complete (152 tests passing, all 7 UAT checks green)

Progress: [██████░░░░] 57%

## Performance Metrics

**Velocity:**
- Total plans completed: 10
- Average duration: --
- Total execution time: --

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1     | 3/3   | --    | --       |
| 2     | 4/4   | --    | --       |
| 3     | 3/3   | --    | --       |

**Recent Trend:**
- Last 5 plans: 02-03, 02-04, 03-01, 03-02, 03-03
- Trend: steady execution

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 7-phase incremental hardening approach derived from requirements; storage before models before execution before analysis
- [Roadmap]: Research recommends AnyIO + httpx for concurrency, Pydantic v2 for schemas, SQLite stdlib for storage, Typer + Rich for CLI
- [Roadmap Revision]: CONF-05/CONF-06 (pre-flight scenario validation) moved from Phase 6 to Phase 2 -- validation must happen before concurrent execution in Phase 3, otherwise compute is wasted on invalid scenarios
- [Roadmap Revision]: IDENT-08 (checkpoint persistence) added to Phase 1 as durable storage foundation -- prerequisite for PKG-01..05 in Phase 7
- [Roadmap Revision]: Phase 6 renamed from "Scenario Validation and Extensibility" to "Extensibility" (now only EXT-01..04)
- [Phase 2 Plan 1]: Keep legacy ScenarioResult in place while adding strict CompletedScenarioResult/FailedScenarioResult schemas for new validation flows
- [Phase 2 Plan 1]: Manifest content hashing uses canonical JSON (`model_dump(mode="json")` + sorted keys) to ignore YAML formatting differences
- [Phase 2 Plan 1]: Manifest loading wraps parse/validation failures with file-path context in ValueError for clearer researcher feedback
- [Phase 2 Plan 2]: Preflight validation aggregates all violations into structured `PreflightError` objects instead of failing fast
- [Phase 2 Plan 2]: Pure-Python Cholesky PSD checks selected to avoid introducing numpy dependency for small correlation matrices
- [Phase 2 Plan 2]: Unknown option types are treated as pass-through (non-error) while enforcing basket dim >= 2 compatibility
- [Phase 2 Plan 3]: `--manifest` is now the authoritative run configuration path; legacy flags remain supported for backward compatibility
- [Phase 2 Plan 3]: Scenario generation now expands Cartesian product across both PDE grid axes and model sweep axes
- [Phase 2 Plan 3]: Source manifest content hash is logged and persisted in run artifact manifest for reproducibility traceability
- [Phase 2 Plan 4]: Keep model_construct for error-aggregation tests needing intentionally invalid Pydantic data; use model_validate only for pure basket-path tests
- [Phase 3 Plan 1]: Use check_same_thread=False for MetadataStore so it can be called from AnyIO worker threads
- [Phase 3 Plan 1]: Classify timeout/connect/protocol and 5xx as retryable; 4xx as non-retryable
- [Phase 3 Plan 2]: Wrap each scenario task in try/except Exception to prevent AnyIO task-group sibling cancellation
- [Phase 3 Plan 2]: Serialize MetadataStore calls with async lock while offloading to worker threads
- [Phase 3 Plan 3]: Bridge Typer sync commands to async orchestrator via anyio.run(partial(...))

### Pending Todos

None yet.

### Blockers/Concerns

- FK PINN backend metric schema needs auditing (which metric keys are stable vs. version-dependent)
- FK PINN backend precision reporting unknown (does it return actual dtype used?)
- FK PINN backend job lifecycle unclear (404 semantics for expired vs. never-existed)
- Actual PINN convergence time distribution unknown (30-min timeout is a guess)
- FK PINN backend checkpoint API needs investigation (how to fetch checkpoints, format, size)

## Session Continuity

Last session: 2026-02-22
Stopped at: Phase 3 UAT complete (7/7 passed, 152 tests, 0 issues)
Resume file: .planning/ROADMAP.md
