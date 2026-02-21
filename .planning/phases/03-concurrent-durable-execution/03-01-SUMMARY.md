---
phase: 03-concurrent-durable-execution
plan: 01
subsystem: async-foundation
tags: [anyio, httpx, tenacity, sqlite, retries, async-client]
requires: []
provides:
  - Phase 3 runtime dependencies for async execution and retry orchestration
  - SQLite schema v2 migration with retry/concurrency/interruption metadata
  - MetadataStore resume/retry APIs for interrupted batch recovery
  - AsyncFKPinnClient API parity with FKPinnClient
  - Retry predicate/decorator utilities with transient error classification
affects: [phase-03-plan-02, phase-03-plan-03, orchestrator, cli, store]
tech-stack:
  added: [anyio, httpx, tenacity]
  patterns: [sqlite migration chaining, async client composition, tenacity retry factory]
key-files:
  created:
    - src/fk_quant_research_accel/retry.py
    - src/fk_quant_research_accel/async_client.py
    - tests/test_retry.py
    - tests/test_async_client.py
  modified:
    - pyproject.toml
    - src/fk_quant_research_accel/store/migrations.py
    - src/fk_quant_research_accel/store/metadata.py
    - tests/test_store.py
key-decisions:
  - "Use check_same_thread=False so MetadataStore can be safely called from AnyIO worker threads."
  - "Classify timeout/connect/protocol and 5xx HTTPStatusError as retryable; treat 4xx as non-retryable."
  - "Keep retry behavior at orchestrator layer and keep AsyncFKPinnClient focused on transport concerns."
patterns-established:
  - "Schema evolution pattern: CURRENT_SCHEMA_VERSION + explicit versioned migration map."
  - "Resume support pattern: query non-terminal scenario rows and persist interruption/retry counters."
completed: 2026-02-21
---

# Phase 3 Plan 01 Summary

Implemented the full Phase 3 foundation for concurrent durable execution.

## Delivered
- Added project dependencies: `anyio`, `httpx`, `tenacity`.
- Upgraded SQLite schema from v1 to v2 with:
  - `scenario_runs.retry_count`
  - `scenario_runs.max_retries`
  - `batch_runs.concurrency_limit`
  - `batch_runs.interrupted_at`
- Enabled thread-safe SQLite connection usage for async worker-thread access with `check_same_thread=False`.
- Extended `MetadataStore` with:
  - `get_incomplete_scenario_runs(batch_run_id)`
  - `update_batch_interrupted(batch_run_id, interrupted_at)`
  - `update_scenario_retry_count(scenario_run_id, retry_count)`
  - `create_batch_run(..., concurrency_limit=1)` support
- Added `retry.py` with:
  - `RETRY_DEFAULTS`
  - `is_retryable_error(exc)`
  - `make_retry_decorator(**overrides)` using Tenacity + exponential jitter + warning logs before sleep
- Added `async_client.py` with `AsyncFKPinnClient`:
  - Async methods: `create_simulation`, `get_simulation`, `get_result`, `list_problems`
  - Async context manager support (`__aenter__`, `__aexit__`, `aclose`)
  - Configured timeout and connection limits based on concurrency
- Added/updated tests:
  - `tests/test_retry.py`
  - `tests/test_async_client.py`
  - `tests/test_store.py` for schema v2 and metadata method coverage

## Verification
- `python3 -m pip install --break-system-packages -e '.[dev]'`
- `python3 -c "import anyio, httpx, tenacity; print('imports ok')"`
- `python3 -c "from fk_quant_research_accel.store.migrations import init_db; import tempfile, os; db = init_db(os.path.join(tempfile.mkdtemp(), 'test.db')); v = db.execute('PRAGMA user_version').fetchone()[0]; print(f'schema v{v}'); assert v == 2; cols = [r[1] for r in db.execute('PRAGMA table_info(scenario_runs)').fetchall()]; assert 'retry_count' in cols; print('v2 migration ok'); db.close()"`
- `python3 -m pytest tests/ -q` -> `134 passed`
- `ruff check src/fk_quant_research_accel/ tests/` -> clean

## Notes
- `types-httpx` was attempted per plan guidance, but no publishable distribution was available; it was intentionally omitted.
