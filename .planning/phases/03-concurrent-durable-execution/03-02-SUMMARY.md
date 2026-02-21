---
phase: 03-concurrent-durable-execution
plan: 02
subsystem: async-orchestrator
tags: [anyio, concurrency, retries, sqlite, resume]
requires:
  - phase: 03-concurrent-durable-execution
    provides: async client, retry predicates, schema v2 metadata fields
provides:
  - Concurrent bounded scenario execution via AnyIO task groups and CapacityLimiter
  - Per-scenario fault isolation so one failure does not cancel sibling tasks
  - Transient HTTP retry for submit/poll/result operations
  - Async-safe SQLite persistence through worker-thread offloading
  - Resume execution for incomplete or forced full re-runs by batch id
affects: [phase-03-plan-03, cli, orchestrator, store]
tech-stack:
  added: []
  patterns: [structured concurrency, retry with jitter, thread-offloaded sqlite, resumable execution]
key-files:
  created:
    - src/fk_quant_research_accel/async_orchestrator.py
    - tests/test_async_orchestrator.py
  modified: []
key-decisions:
  - "Wrap each scenario task in try/except Exception to prevent AnyIO task-group sibling cancellation."
  - "Serialize MetadataStore calls with an async lock while still executing sqlite operations via anyio.to_thread.run_sync."
  - "Keep retry behavior at orchestrator call sites with async retry helper and retryable-error predicate."
patterns-established:
  - "Shared execution path via _execute_scenarios_concurrent used by both run_batch_async and resume_batch_async."
  - "Resume selection pattern using get_incomplete_scenario_runs unless force=True."
completed: 2026-02-21
---

# Phase 3 Plan 02 Summary

Implemented the async concurrent orchestrator and complete test coverage for concurrent execution, retry behavior, and resumability.

## Delivered
- Added `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/async_orchestrator.py` with:
  - `run_batch_async(...)`
  - `resume_batch_async(...)`
  - bounded concurrency using `CapacityLimiter` + `create_task_group`
  - per-scenario fault isolation (`except Exception`) to prevent sibling cancellation
  - transient retry support for `create_simulation`, `get_simulation`, and `get_result`
  - non-blocking polling via `anyio.sleep(...)` + jitter
  - checkpoint retrieval support (`checkpoint_url` and inline checkpoint payload)
  - result format compatibility with sync orchestrator record schema
  - sorted return values by score
- Ensured all SQLite metadata operations from async paths use `anyio.to_thread.run_sync(...)` through `_run_store(...)`.
- Added concurrency-safe store access by serializing metadata calls with an async lock to avoid sqlite interface errors under high parallelism.
- Added `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_async_orchestrator.py` covering:
  - basic async batch run behavior
  - concurrency limit enforcement
  - single failure isolation
  - transient retry success path
  - non-retryable immediate failure
  - resume incomplete-only behavior
  - resume force behavior
  - missing batch errors
  - sqlite thread access path
  - result record key compatibility

## Verification
- `python3 -c "from fk_quant_research_accel.async_orchestrator import run_batch_async, resume_batch_async; print('imports ok')"`
- `ruff check src/fk_quant_research_accel/async_orchestrator.py tests/test_async_orchestrator.py`
- `python3 -m pytest tests/test_async_orchestrator.py -q` -> `10 passed`
- `ruff check src/fk_quant_research_accel/ tests/` -> clean
- `python3 -m pytest tests/ -q` -> `144 passed`

## Notes
- SQLite contention surfaced during full-suite runs under concurrent tasks; fixed by serializing metadata operations while preserving worker-thread offloading and non-blocking event loop behavior.
