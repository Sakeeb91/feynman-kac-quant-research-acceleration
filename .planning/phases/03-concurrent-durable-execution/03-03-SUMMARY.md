---
phase: 03-concurrent-durable-execution
plan: 03
subsystem: cli
tags: [typer, anyio, async-orchestrator, resume]
requires:
  - phase: 03-concurrent-durable-execution
    provides: run_batch_async and resume_batch_async orchestrator APIs
provides:
  - Async `run-batch` CLI wiring with concurrency and retry controls
  - New `resume-batch` command for crash/interruption recovery
  - CLI tests updated for async invocation and resume behavior
affects: [cli, tests, phase-03-usability]
tech-stack:
  added: []
  patterns: [sync-to-async bridge with anyio.run, partial-based invocation capture in tests]
key-files:
  created:
    - .planning/phases/03-concurrent-durable-execution/03-03-SUMMARY.md
  modified:
    - src/fk_quant_research_accel/cli.py
    - tests/test_cli.py
key-decisions:
  - "Bridge Typer sync commands to async orchestrator entry points via anyio.run(partial(...))."
  - "Preserve manifest and legacy-flag compatibility while switching run-batch to async execution path."
  - "Surface resume-batch missing batch IDs as exit code 1 with structured error logging."
patterns-established:
  - "CLI async orchestration wrapper pattern reused across run-batch and resume-batch."
  - "Tests assert callable/keyword wiring by intercepting anyio.run rather than spinning event loops."
completed: 2026-02-21
---

# Phase 3 Plan 03 Summary

Implemented CLI integration for concurrent async execution and resuming interrupted batches.

## Delivered
- Updated `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/cli.py`:
  - `run-batch` now executes through `anyio.run(partial(run_batch_async, ...))`.
  - Added `--concurrency` (default `20`) and `--max-retries` (default `3`) to `run-batch`.
  - Preserved manifest mode and legacy flag mode behavior.
  - Added `resume-batch` command with:
    - positional `batch_run_id`
    - `--force`, `--concurrency`, `--max-retries`, `--base-url`
    - `--poll-seconds`, `--max-wait-seconds`, `--db-path`, `--artifacts-dir`, `--output`
  - `resume-batch` bridges to `resume_batch_async` with `anyio.run(partial(...))`.
  - Handles missing/nonexistent batch as `ValueError` -> logs and exits with code `1`.

- Updated `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_cli.py`:
  - Added async-path assertions for manifest and legacy `run-batch` invocations.
  - Added coverage for default `--concurrency` and default `--max-retries`.
  - Added `resume-batch --help` coverage.
  - Added `resume-batch` invocation and nonexistent-batch error handling tests.
  - Kept and expanded manifest preflight regression coverage.

## Verification
- `python3 -m fk_quant_research_accel.cli --help`
- `python3 -m fk_quant_research_accel.cli run-batch --help`
- `python3 -m fk_quant_research_accel.cli resume-batch --help`
- `python3 -m pytest tests/test_cli.py -q` -> `20 passed`
- `python3 -m pytest tests/ -q` -> `152 passed`
- `ruff check src/fk_quant_research_accel/ tests/` -> clean

## Outcome
Phase 3 CLI is now fully wired to the async orchestrator and exposes researcher-facing controls for throughput (`--concurrency`) and resilience (`--max-retries`, `resume-batch`).
