# Architecture

**Analysis Date:** 2026-02-19

## Pattern Overview

**Overall:** Layered client-orchestrator pattern with separation of concerns across HTTP communication, scenario generation, batch execution, and reporting.

**Key Characteristics:**
- **Stateless HTTP client** wrapping external FK PINN API endpoints
- **Scenario-driven design** using immutable data classes for reproducibility
- **Asynchronous polling** for long-running simulations
- **Normalized result capture** with consistent metrics extraction and scoring
- **Linear composition** of functions for batch workflow (no complex state machines)

## Layers

**API Integration Layer:**
- Purpose: Abstract HTTP communication with FK PINN backend
- Location: `src/fk_quant_research_accel/client.py`
- Contains: `FKPinnClient` class with polling logic and request/response handling
- Depends on: `requests` library
- Used by: Orchestration layer

**Orchestration Layer:**
- Purpose: Scenario generation, batch submission, result collection, and ranking
- Location: `src/fk_quant_research_accel/orchestrator.py`
- Contains: `Scenario`, `BatchConfig` dataclasses and workflow functions
- Depends on: Client layer, reporting layer (for scoring)
- Used by: CLI layer

**Reporting Layer:**
- Purpose: Result aggregation, metric scoring, and CSV export
- Location: `src/fk_quant_research_accel/reporting.py`
- Contains: Score computation and CSV writing utilities
- Depends on: Standard library (csv, pathlib)
- Used by: Orchestration layer, CLI layer

**CLI/Interface Layer:**
- Purpose: Command-line argument parsing and workflow invocation
- Location: `src/fk_quant_research_accel/cli.py`
- Contains: `main()` entry point, argument parser, and display logic
- Depends on: All internal layers
- Used by: End user via `python -m fk_quant_research_accel.cli`

## Data Flow

**Batch Experiment Workflow:**

1. **Scenario Generation** (orchestrator)
   - Input: Lists of dimensions, volatilities, correlations, option types
   - Process: Cross-product via `itertools.product()` creates N scenarios
   - Output: List of immutable `Scenario` objects

2. **Batch Configuration** (orchestrator)
   - Input: Training hyperparameters (steps, batch_size, learning_rate, etc.)
   - Process: Encapsulated in `BatchConfig` dataclass
   - Output: Converted to API payload via `to_payload()`

3. **Simulation Submission** (client → orchestrator)
   - Input: Scenario parameters + training config
   - Process: `client.create_simulation()` posts to `/api/v1/simulations`
   - Output: Simulation ID and initial response

4. **Polling Loop** (client → orchestrator)
   - Input: Simulation ID
   - Process: `client.wait_until_terminal()` polls `/api/v1/simulations/{id}` every 1.5s until status in {completed, failed, cancelled}
   - Output: Terminal simulation object

5. **Result Collection** (client → orchestrator)
   - Input: Simulation ID (from terminal simulation)
   - Process: `client.get_result()` fetches from `/api/v1/results/{id}`
   - Output: Result envelope with metrics

6. **Metric Extraction & Scoring** (reporting → orchestrator)
   - Input: Raw result metrics and simulation status
   - Process: Normalize metrics (handle missing/null values), compute composite score
   - Output: Scored record dict ready for ranking

7. **Ranking & Output** (orchestrator → CLI)
   - Input: List of scored records
   - Process: Sort by score ascending (lower is better)
   - Output: Ranked list written to CSV

**State Management:**
- **Immutable inputs**: `Scenario`, `BatchConfig` defined as frozen dataclasses
- **Polling state**: Transient (deadline-based in `wait_until_terminal()`)
- **Batch results**: Accumulated in-memory list, no database persistence
- **Output state**: Written to filesystem (CSV file)

## Key Abstractions

**Scenario:**
- Purpose: Encapsulates a single experimental configuration (dim, volatility, correlation, option_type)
- Examples: `src/fk_quant_research_accel/orchestrator.py:14-26`
- Pattern: Frozen dataclass with `as_parameters()` conversion method for API payload

**BatchConfig:**
- Purpose: Encapsulates training hyperparameters (n_steps, batch_size, learning_rate)
- Examples: `src/fk_quant_research_accel/orchestrator.py:29-42`
- Pattern: Frozen dataclass with `to_payload()` for API serialization

**FKPinnClient:**
- Purpose: Type-safe HTTP client for FK PINN backend
- Examples: `src/fk_quant_research_accel/client.py:15-69`
- Pattern: Frozen dataclass with private helper methods (`_get`, `_post`, `_url`) and public API methods (`create_simulation`, `get_simulation`, `wait_until_terminal`)

**Score Function:**
- Purpose: Rank simulations by quality (lower is better)
- Examples: `src/fk_quant_research_accel/reporting.py:10-24`
- Pattern: Single pure function with explicit penalty logic (failed status → inf, missing train_loss → inf, gradient norm penalty on success)

## Entry Points

**CLI Entry Point:**
- Location: `src/fk_quant_research_accel/cli.py:88-89`
- Triggers: `python -m fk_quant_research_accel.cli run-batch [args]`
- Responsibilities:
  - Parse command-line arguments (base_url, dimensions, volatilities, etc.)
  - Instantiate `FKPinnClient` with user-provided base_url
  - Generate scenarios via `generate_black_scholes_scenarios()`
  - Build `BatchConfig` from parsed args
  - Call `run_batch()` orchestrator
  - Write results to CSV
  - Print leaderboard summary to stdout

**Module Export Point:**
- Location: `src/fk_quant_research_accel/__init__.py`
- Exports: `FKPinnClient`, `BatchConfig`, `Scenario`, `generate_black_scholes_scenarios`, `run_batch`
- Enables: Programmatic use as library (e.g., `from fk_quant_research_accel import run_batch`)

## Error Handling

**Strategy:** Fail-fast with explicit error propagation

**Patterns:**
- **HTTP errors**: `requests.raise_for_status()` on all requests (client.py:25, 30)
- **Timeout errors**: `TimeoutError` raised if simulation doesn't reach terminal status within deadline (client.py:68)
- **Missing metrics**: Handled gracefully with None defaults and infinity scoring (reporting.py:19-21)
- **Invalid arguments**: argparse raises SystemExit on validation failure (cli.py)
- **File I/O**: `Path.parent.mkdir(parents=True, exist_ok=True)` ensures output directory exists (reporting.py:29)

## Cross-Cutting Concerns

**Logging:** Not implemented. Uses `print()` for CLI output only (cli.py:21-30, 81).

**Validation:** Input validation delegated to:
- argparse for CLI arguments (cli.py:33-51)
- Dataclass frozen state for immutability (Scenario, BatchConfig)
- API response parsing via `.raise_for_status()` and `.json()`

**Authentication:** Not applicable. Client assumes backend is accessible without authentication (requests sent to provided base_url).

**Timeouts:** Configurable per-operation:
- HTTP timeout: Default 30s per request (client.py:18)
- Polling timeout: Default 30m max wait (client.py:59)
- Polling interval: Default 1.5s between polls (client.py:58)

---

*Architecture analysis: 2026-02-19*
