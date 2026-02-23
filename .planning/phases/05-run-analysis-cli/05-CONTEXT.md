# Phase 5: Run Analysis CLI - Context

**Gathered:** 2026-02-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Query, compare, and drill into past experiment runs from the command line. Three commands: `list-runs` (summary listing), `compare-runs` (two-run delta report), `show-run` (single-run deep dive). Turns individual batches into a systematic research program.

Requirements: IDENT-05, IDENT-06, IDENT-07.

</domain>

<decisions>
## Implementation Decisions

### Run identification
- Canonical ID: existing `batch_run_id` UUID from MetadataStore
- Accept unambiguous short prefix (first 8+ characters) for convenience
- Lightweight selectors: `latest` (most recent) and `latest~N` (Nth most recent run)
- No custom aliases in Phase 5 — skip new persistence surface; defer to future phase

### Comparison display
- Compare exactly two runs in Phase 5 (no multi-run comparison)
- Align rows by scenario parameter key: `(dim, volatility, correlation, option_type, model_config)`
- Per-row columns: `run_a` value, `run_b` value, `delta_abs`, `delta_pct` for core metrics: score, train_loss, grad_norm, progress
- Status mismatch flags when scenarios differ in completion status
- Summary block at top/bottom: matched scenario count, missing-on-each-side counts, win/loss count on score

### Filtering & sorting
- `list-runs` filters: `--status`, `--from`, `--to`, `--min-score`, `--max-score`, `--git-sha`, `--manifest-hash`
- Default sort: newest first (`created_at DESC`)
- Pagination: `--limit` (default 20), `--offset` (default 0)
- `compare-runs` default: completed scenarios only, with `--all-status` opt-in to include failed/pending

### Output formatting
- Auto-detect output target: Rich table on TTY, plain text when piped
- Explicit override: `--format table|json|csv`
- `--verbose` flag for dense vs compact row display
- `list-runs` default columns: run_id, created_at, status, scenario_count, completed/failed, best_score, median_score

### Claude's Discretion
- Exact Rich table styling and color palette for health labels
- Column truncation/wrapping strategy for narrow terminals
- JSON/CSV field ordering and naming conventions
- Error message formatting when run IDs are ambiguous or not found
- Whether `show-run` uses Rich panels, tables, or mixed layout

</decisions>

<specifics>
## Specific Ideas

- Run identification order was deliberate: lock IDs first since comparison and filtering depend on how runs are referenced
- The `latest~N` selector mirrors git's `HEAD~N` syntax — familiar to researchers who use git
- Scenario alignment key `(dim, volatility, correlation, option_type, model_config)` must match how scenarios are generated from manifests (Cartesian product axes)
- Win/loss summary in compare-runs should make it immediately obvious which run was better overall

</specifics>

<deferred>
## Deferred Ideas

- Custom run aliases (e.g., `baseline`, `best-so-far`) — requires new persistence surface, separate phase
- Multi-run comparison (3+ runs) — Phase 5 locks at exactly two
- Export comparison reports to file (HTML/PDF) — future enhancement

</deferred>

---

*Phase: 05-run-analysis-cli*
*Context gathered: 2026-02-23*
