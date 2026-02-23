# Phase 05-01 Summary

## Scope Delivered

Implemented Phase 05 Plan 01 end-to-end:

- schema migration `v2 -> v3` with `manifest_hash` support,
- `MetadataStore` listing/prefix query capabilities for run analysis,
- new `run_analysis` package (`resolver`, `queries`, `formatters`),
- `list-runs` CLI command with filtering, pagination, and output formats,
- comprehensive tests across store, run analysis, and CLI layers.

## Key Changes

### Storage and Migration

- Bumped schema version to `3` in migrations.
- Added `_migrate_v2_to_v3` to append `manifest_hash TEXT` to `batch_runs`.
- Extended `MetadataStore.create_batch_run` to persist `manifest_hash`.
- Wired manifest hash persistence from both sync and async orchestrators.

### MetadataStore Query Surface

- Added `list_batch_runs(...)` with:
  - filters: `status`, `from_date`, `to_date`, `git_sha`, `manifest_hash`,
  - score filters: `min_score`, `max_score` via `HAVING` on aggregated `best_score`,
  - pagination: `limit`, `offset`,
  - ordering allowlist: `created_at DESC|ASC`,
  - aggregation of `best_score` from completed scenario rows.
- Added `find_batch_runs_by_prefix(prefix)`.

### Run Analysis Package

- Added `resolve_run_id(selector, store)` supporting:
  - full UUID / UUID prefix (minimum 8 chars),
  - `latest` and `latest~N`,
  - clear errors for short, ambiguous, and not-found selectors.
- Added `list_runs_with_metrics(store, **filters)` computing `median_score` from completed scenario scores.
- Added run output formatters:
  - `get_effective_format(...)` (TTY auto-detection),
  - `emit_runs_table(...)`,
  - `emit_json(...)`,
  - `emit_csv(...)`.

### CLI

- Added `list-runs` command with options:
  - `--db-path`, `--status`, `--from`, `--to`, `--min-score`, `--max-score`,
  - `--git-sha`, `--manifest-hash`, `--limit`, `--offset`,
  - `--format table|json|csv`, `--verbose`.
- Connected CLI path:
  - `MetadataStore` -> `list_runs_with_metrics` -> format detection -> renderer.

## Test Coverage Added

- `tests/test_store.py`
  - v3 migration assertions,
  - all list filters/pagination/score filters,
  - prefix lookup variants,
  - manifest hash persistence.
- `tests/test_run_analysis.py`
  - resolver selector behavior and errors,
  - median score enrichment,
  - format detection and renderer behavior.
- `tests/test_cli.py`
  - `list-runs` empty DB, populated DB, status filter, pagination,
  - table/csv/json output behavior.

## Verification Results

- `python3 -m pytest tests/ -q` -> `237 passed`
- `python3 -m fk_quant_research_accel.cli list-runs --help` -> command/flags present
- `python3 -c "from fk_quant_research_accel.store.migrations import CURRENT_SCHEMA_VERSION; assert CURRENT_SCHEMA_VERSION == 3"` -> pass
- `python3 -c "from fk_quant_research_accel.run_analysis import resolve_run_id, list_runs_with_metrics, get_effective_format"` -> pass
- `ruff check src/fk_quant_research_accel/` -> pass
