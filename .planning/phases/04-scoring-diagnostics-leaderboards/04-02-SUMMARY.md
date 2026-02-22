---
phase: 04-scoring-diagnostics-leaderboards
plan: 02
subsystem: orchestrator-cli-leaderboard
tags: [execute, orchestrator, async, scoring, diagnostics, leaderboard, rich]
requires:
  - phase: 04-scoring-diagnostics-leaderboards
    provides: scorer registry, diagnostics classifier, pareto utilities
provides:
  - Sync and async orchestrators wired to configurable scoring + convergence diagnostics
  - Pareto post-hoc rescoring path in batch and resume execution
  - Rich leaderboard renderer on stderr with health color coding
  - CLI integration replacing legacy top_scenario structlog output
affects: [orchestrator, async_orchestrator, cli, leaderboard, tests]
tech-stack:
  added: []
  patterns: [scorer injection through async call chain, post-hoc pareto reranking, rich table rendering]
key-files:
  created:
    - .planning/phases/04-scoring-diagnostics-leaderboards/04-02-SUMMARY.md
    - src/fk_quant_research_accel/leaderboard.py
    - tests/test_leaderboard.py
  modified:
    - src/fk_quant_research_accel/orchestrator.py
    - src/fk_quant_research_accel/async_orchestrator.py
    - src/fk_quant_research_accel/cli.py
    - tests/test_orchestrator.py
    - tests/test_async_orchestrator.py
    - tests/test_cli.py
key-decisions:
  - "Resolve scorer once per run/resume call and inject it into async worker chain instead of recalculating per record."
  - "Assign failed records convergence health as exploding at failure-record construction time."
  - "Apply Pareto ranking only after all records are present to preserve non-dominated sorting semantics."
  - "Render leaderboard to stderr via Rich to avoid interleaving with structured stdout logs."
patterns-established:
  - "`run_batch_async` and `resume_batch_async` now both support `scoring_config` and consistent post-processing."
  - "CLI tests patch `render_leaderboard` directly rather than asserting legacy `_log_top` events."
completed: 2026-02-22
---

# Phase 4 Plan 02 Summary

Implemented orchestration and CLI integration for scoring strategies, convergence diagnostics, and Rich leaderboard output.

## Delivered
- Updated `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/orchestrator.py`:
  - Added optional `scoring_config: ScoringConfig | None` to `run_batch`.
  - Replaced hardcoded score logic with `get_scorer(...)` dispatch.
  - Added `convergence_health` to completed and failure records.
  - Added Pareto post-hoc rescoring with `assign_pareto_scores(...)`.

- Updated `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/async_orchestrator.py`:
  - Added optional `scoring_config: ScoringConfig | None` to `run_batch_async` and `resume_batch_async`.
  - Injected scorer callable through `_execute_scenarios_concurrent -> _execute_scenario_safe -> _submit_and_poll_scenario`.
  - Replaced `compute_score` with scorer invocation and attached `convergence_health` diagnostics.
  - Added exploding health to failure records.
  - Added Pareto post-hoc rescoring in both run and resume paths.

- Added `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/leaderboard.py`:
  - `render_leaderboard(...)` Rich table renderer.
  - Health color map (`healthy` green, `oscillating`/`stagnating` yellow, `exploding` red).
  - Formatting helpers for scores, health text, and correlation display.

- Updated `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/src/fk_quant_research_accel/cli.py`:
  - Removed `_log_top` structlog emission path.
  - Added `render_leaderboard(rows)` for both `run-batch` and `resume-batch`.
  - Manifest mode now passes `experiment.scoring` to `run_batch_async(..., scoring_config=...)`.

- Added/updated tests:
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_orchestrator.py`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_async_orchestrator.py`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_leaderboard.py`
  - `/Users/sakeeb/Code repositories/feynman-kac-quant-research-acceleration/tests/test_cli.py`

## Verification
- `python3 -m pytest tests/test_orchestrator.py tests/test_async_orchestrator.py -q` -> passed
- `python3 -m pytest tests/test_leaderboard.py -q` -> passed
- `python3 -m pytest tests/test_cli.py -q` -> passed
- `python3 -m pytest tests/ -q` -> `204 passed`
- `python3 -c "from fk_quant_research_accel.leaderboard import render_leaderboard"` -> passed
- `python3 -c "from fk_quant_research_accel.async_orchestrator import run_batch_async, resume_batch_async; from fk_quant_research_accel.orchestrator import run_batch"` -> passed
- `rg -n "_log_top|top_scenario" src/fk_quant_research_accel/cli.py tests/test_cli.py` -> no matches

## Outcome
Plan 04-02 is complete: both orchestrators now emit convergence health and respect scoring strategy, Pareto rescoring is applied when requested, and CLI output uses a Rich leaderboard with color-coded health labels.
