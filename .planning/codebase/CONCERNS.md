# Codebase Concerns

**Analysis Date:** 2026-02-19

## Tech Debt

**Missing Error Handling in CLI Input Parsing:**
- Issue: Float and integer parsing in CLI accept malformed input without validation
- Files: `src/fk_quant_research_accel/cli.py` (lines 13-18)
- Impact: Invalid command-line arguments (e.g., `--dimensions "five,ten"` or `--volatilities "0.2x"`) will raise unhandled exceptions, terminating the batch without user-friendly error messages
- Fix approach: Wrap `_parse_int_list()` and `_parse_float_list()` with try-catch blocks; catch `ValueError` and return informative CLI error messages before batch submission

**No Retry Logic for Transient Network Failures:**
- Issue: HTTP client makes single attempts with no retry mechanism for failed requests
- Files: `src/fk_quant_research_accel/client.py` (lines 23-31)
- Impact: Temporary network glitches, service restarts, or transient 5xx errors from FK PINN backend will fail the entire batch. A single timeout or 503 error loses all accumulated progress
- Fix approach: Implement exponential backoff retry logic (e.g., 3-5 attempts with 1-2s base delay); consider using `requests.adapters.HTTPAdapter` with `Retry` strategy or `tenacity` library

**No Validation of Backend Response Schema:**
- Issue: Code assumes FK PINN API responses match expected shape; no schema validation
- Files: `src/fk_quant_research_accel/orchestrator.py` (lines 86-87), `src/fk_quant_research_accel/client.py` (line 25-26)
- Impact: If FK PINN API changes response structure or returns incomplete data, `result_envelope["item"]` or `simulation["status"]` will raise `KeyError`, crashing the batch mid-run
- Fix approach: Validate response structure using pydantic models or simple dict key checks; catch `KeyError` with informative error that indicates upstream API contract violation

**Hardcoded Problem ID in Orchestrator:**
- Issue: `run_batch()` always uses `"black_scholes"` as problem_id
- Files: `src/fk_quant_research_accel/orchestrator.py` (line 73)
- Impact: Prevents reuse of `run_batch()` for other problem types (e.g., "option_pricing", "portfolio_optimization"); only Black-Scholes scenarios can be executed
- Fix approach: Add `problem_id` parameter to `run_batch()` and `BatchConfig`, or make it configurable via CLI argument

**No Handling of Partial Batch Failures:**
- Issue: If a simulation fails or times out, `orchestrator.run_batch()` still includes the failed record in results with `score=inf`
- Files: `src/fk_quant_research_accel/orchestrator.py` (lines 79-105)
- Impact: Failed simulations pollute leaderboard output; users can't distinguish between successful and failed scenarios visually. No cleanup of submitted jobs if downstream fails
- Fix approach: Separate successful and failed records; provide summary counts (e.g., "5/20 simulations completed successfully"); consider cancellation logic if batch-wide failure threshold exceeded

## Known Bugs

**Metrics Extraction Fallback Silently Swallows Missing Data:**
- Symptoms: When metrics are missing or malformed, `record["train_loss"] = metrics.get("loss", metrics.get("train_loss"))` returns `None`, but downstream code does not distinguish between "not computed" and "zero loss"
- Files: `src/fk_quant_research_accel/orchestrator.py` (lines 97-100)
- Trigger: Any simulation returning `result["metrics"] = {}` or missing `"loss"` and `"train_loss"` keys will silently assign `None`
- Workaround: Check CSV output for `None` values in loss columns; manually verify completion status

**Float Comparison in Score Sorting:**
- Symptoms: Sorting by `score` uses direct float comparison; `float("inf")` values sort to end, but near-equal floats may have unstable order
- Files: `src/fk_quant_research_accel/orchestrator.py` (line 105)
- Trigger: Two scenarios with scores like `0.1234567890123` and `0.1234567890124` may reorder unexpectedly if floating-point rounding differs
- Workaround: Use strict tie-breaking (e.g., sort by scenario parameters secondarily)

## Security Considerations

**No HTTPS Verification for Backend Connection:**
- Risk: Client accepts any SSL certificate without verification if backend uses self-signed certs; vulnerable to MITM attacks in production
- Files: `src/fk_quant_research_accel/client.py` (lines 24, 29)
- Current mitigation: Default `requests` behavior verifies HTTPS certificates; but no explicit `verify=True` enforced
- Recommendations:
  - Add explicit `verify=True` or CA bundle path parameter to `FKPinnClient`
  - Document and warn if `base_url` uses HTTP (insecure)
  - Support `REQUESTS_CA_BUNDLE` environment variable for production deployments

**No Rate Limiting or Quota Management:**
- Risk: Client submits all scenarios synchronously without delay; could overwhelm FK PINN backend or trigger rate limits
- Files: `src/fk_quant_research_accel/orchestrator.py` (lines 71-77)
- Current mitigation: None
- Recommendations:
  - Add throttling between simulation submissions (e.g., 0.1-0.5s delay per submission)
  - Implement backpressure: pause if polling detects backend queue saturation
  - Log submission rate and provide warnings if exceeding typical backend capacity

## Performance Bottlenecks

**Synchronous Polling Blocks Entire Batch:**
- Problem: `orchestrator.run_batch()` blocks in a loop polling each simulation sequentially
- Files: `src/fk_quant_research_accel/orchestrator.py` (lines 79-84)
- Cause: No concurrent polling; if 100 simulations are submitted and each takes 30s, total wait is 3000s+ sequentially
- Improvement path:
  - Refactor to concurrent polling using `asyncio` or `concurrent.futures`
  - Poll all simulations in parallel; add concurrent request limits (e.g., max 10 concurrent polls)
  - Expected speedup: 10-50x faster for large batches

**No Caching of Simulation Status:**
- Problem: Every time CLI calls `client.wait_until_terminal()`, it polls the same simulation ID repeatedly, even if status was just checked
- Files: `src/fk_quant_research_accel/client.py` (lines 55-68)
- Cause: No cache layer; each `get_simulation()` makes a fresh HTTP request
- Improvement path: Add optional in-memory cache with TTL (e.g., cache for 1s); optionally persist to disk for resumable runs

**CSV Writing Without Batching:**
- Problem: `write_csv()` opens, writes, and closes file once; no incremental streaming
- Files: `src/fk_quant_research_accel/reporting.py` (lines 27-40)
- Cause: Writes entire result list at end; if batch is interrupted, no partial results saved
- Improvement path: Stream results to CSV as they complete; save checkpoints every N simulations

## Fragile Areas

**Scenario Parameter Cross-Product Growth:**
- Files: `src/fk_quant_research_accel/orchestrator.py` (lines 45-57)
- Why fragile: `itertools.product()` creates exponential growth; `dimensions=[2..20] × volatilities=[5] × correlations=[10] × option_types=[2]` = 2000 scenarios without user awareness
- Safe modification: Validate and warn if total scenario count > 1000; add `--max-scenarios` limiter; log cross-product size before submission
- Test coverage: Only 1 test for cross-product (16 scenarios); no tests for large grids or edge cases

**FK PINN API Contract Assumptions:**
- Files: `src/fk_quant_research_accel/client.py`, `src/fk_quant_research_accel/orchestrator.py`
- Why fragile: Code assumes:
  - `create_simulation()` returns dict with `"id"` key
  - `get_simulation()` returns dict with `"status"` key in TERMINAL_STATUSES
  - `get_result()` returns dict with `"item"` key containing metrics
  - Metrics dict contains optional `"loss"` or `"train_loss"` keys
  - If any assumption violated, batch fails with `KeyError`
- Safe modification: Define response schema (e.g., Pydantic model); validate before processing
- Test coverage: Zero tests for client methods (mocking not implemented)

**CLI Argument Parsing Without Validation:**
- Files: `src/fk_quant_research_accel/cli.py` (lines 38-48)
- Why fragile: No validation that values are sensible:
  - `--dimensions` accepts `[0, -1, 1000000]` without error
  - `--volatilities` accepts `[-0.5, 10000.0]` (nonsensical for finance)
  - `--poll-seconds` accepts `0` (busy-wait on CPU)
  - `--max-wait-seconds` accepts `1` (timeout before first poll)
  - `--batch-size`, `--n-steps` accept `0`
- Safe modification: Add range validation; warn or reject out-of-range values before batch submission
- Test coverage: Zero tests for CLI argument parsing

## Scaling Limits

**Hard Timeout for All Simulations:**
- Current capacity: Single polling loop with 30-minute default timeout per simulation
- Limit: Batches with >100 scenarios can take hours; no way to scale to 1000+ scenarios efficiently
- Scaling path:
  1. Implement concurrent polling (addresses performance bottleneck above)
  2. Add dynamic timeout adjustment based on scenario complexity (e.g., higher dims = longer timeouts)
  3. Support checkpoint/resume: save completed simulations to disk; allow re-running failed subset

**Memory Growth with Large Batches:**
- Current capacity: All simulation records held in memory until batch completes
- Limit: 10k+ scenarios with rich metrics = MB of RAM; no streaming to disk
- Scaling path: Stream results to CSV incrementally; use generators for large result sets

**No Pagination or Windowing for Results:**
- Current capacity: `list_problems()` fetches all problems at once
- Limit: If FK PINN API returns 10k+ problem definitions, no way to page
- Scaling path: Add optional `offset`/`limit` parameters; handle paginated responses

## Dependencies at Risk

**Requests Library Without Pinned Version:**
- Risk: `requests>=2.32.0` allows any newer version; major version changes could break compatibility
- Impact: Future `requests` 3.x may change request API, timeout semantics, or SSL defaults
- Migration plan: Pin to minor version range (e.g., `requests>=2.32.0,<3.0.0`); add integration tests with FK PINN backend

**No Type Checking in CI:**
- Risk: `mypy>=1.10.0` is installed but never run in CI pipeline
- Impact: Type errors can hide until runtime; no static validation of FK PINN client API contracts
- Migration plan: Add `mypy` check step to CI; configure `mypy --strict` for `src/` directory

## Missing Critical Features

**No Simulation Cancellation:**
- Problem: If batch fails after 50/100 simulations submitted, submitted jobs continue running on backend
- Blocks: Users can't stop runaway batches; wastes backend resources
- Solution: Add `cancel_batch()` method to client; call on CLI interrupt (SIGINT)

**No Result Persistence Between Runs:**
- Problem: If CLI crashes mid-batch, all progress is lost; must resubmit entire batch
- Blocks: Unreliable for long-running research; requires manual resume logic
- Solution: Checkpoint submitted simulation IDs to disk; detect and resume on CLI restart

**No Observability/Logging:**
- Problem: No structured logging; CLI only prints top 10 results
- Blocks: Debugging failed batches requires re-running with verbose flags
- Solution: Add `--log-level` flag; log all simulation submissions, poll attempts, failures to file

**No Multi-Backend Support:**
- Problem: Hardcoded assumption that only 1 FK PINN backend exists
- Blocks: Can't distribute batch across multiple backends for parallelism
- Solution: Accept list of `--base-urls`; distribute scenarios round-robin across backends

## Test Coverage Gaps

**Untested Client Methods:**
- What's not tested: `FKPinnClient._get()`, `_post()`, `create_simulation()`, `get_simulation()`, `get_result()`, `wait_until_terminal()`
- Files: `src/fk_quant_research_accel/client.py`
- Risk: HTTP errors, malformed responses, timeout behavior never validated
- Priority: High

**Untested CLI Argument Parsing:**
- What's not tested: All CLI argument combinations; edge cases like empty lists, negative numbers, malformed floats
- Files: `src/fk_quant_research_accel/cli.py`
- Risk: Unexpected CLI crashes with unhelpful error messages
- Priority: Medium

**Untested Orchestrator.run_batch():**
- What's not tested: Batch execution with simulated backend; failure scenarios; partial batch failures
- Files: `src/fk_quant_research_accel/orchestrator.py`
- Risk: Integration issues hidden until real backend is used
- Priority: High

**Untested Reporting CSV Writing:**
- What's not tested: CSV output with special characters, unicode, very large result sets
- Files: `src/fk_quant_research_accel/reporting.py`
- Risk: CSV corruption or unreadable output in edge cases
- Priority: Low

---

*Concerns audit: 2026-02-19*
