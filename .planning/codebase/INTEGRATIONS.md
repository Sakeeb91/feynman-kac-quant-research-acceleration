# External Integrations

**Analysis Date:** 2026-02-19

## APIs & External Services

**Feynman-Kac PINN Backend:**
- Service: Custom research simulation backend for PINN (Physics-Informed Neural Network) based option pricing
  - What it's used for: Problem definitions, simulation job submission, result retrieval
  - SDK/Client: Custom HTTP client in `src/fk_quant_research_accel/client.py`
  - Auth: None (HTTP requests without authentication)

## API Endpoints

**Problem Management:**
- `GET /api/v1/problems` - List available problem definitions
  - Implementation: `FKPinnClient.list_problems()` in `src/fk_quant_research_accel/client.py:33-34`

**Simulation Lifecycle:**
- `POST /api/v1/simulations` - Submit a new simulation job with problem ID, parameters, and training config
  - Implementation: `FKPinnClient.create_simulation()` in `src/fk_quant_research_accel/client.py:36-47`
  - Parameters: `problem_id` (string), `parameters` (dict with dim/volatility/correlation/option_type), `training_config` (dict with n_steps/batch_size/n_mc_paths/learning_rate)

- `GET /api/v1/simulations/{simulation_id}` - Retrieve simulation status and metadata
  - Implementation: `FKPinnClient.get_simulation()` in `src/fk_quant_research_accel/client.py:49-50`
  - Returns: JSON object with `id`, `status` (one of: pending, running, completed, failed, cancelled), and other metadata

**Results:**
- `GET /api/v1/results/{simulation_id}` - Retrieve simulation output and metrics
  - Implementation: `FKPinnClient.get_result()` in `src/fk_quant_research_accel/client.py:52-53`
  - Returns: JSON envelope with `item` object containing `progress`, `metrics` (with loss, val_loss, lr, grad_norm fields)

## Request/Response Patterns

**HTTP Client Configuration:**
- Timeout: 30 seconds (configurable via `FKPinnClient.timeout` dataclass field)
- JSON Content-Type for POST requests
- Automatic error raising via `response.raise_for_status()` on 4xx/5xx responses
- Location: `src/fk_quant_research_accel/client.py`

**Polling Strategy:**
- Asynchronous polling for job completion in `FKPinnClient.wait_until_terminal()`
  - Default poll interval: 1.5 seconds
  - Default max wait: 1800 seconds (30 minutes)
  - Terminal statuses: `completed`, `failed`, `cancelled`
  - Raises `TimeoutError` if simulation doesn't reach terminal state within deadline

## Data Flow

**Batch Execution Sequence:**

1. **Scenario Generation** (`src/fk_quant_research_accel/orchestrator.py:45-57`)
   - Generate Cartesian product of Black-Scholes parameter combinations
   - Create `Scenario` dataclass instances with dim, volatility, correlation, option_type

2. **Simulation Submission** (`src/fk_quant_research_accel/orchestrator.py:60-77`)
   - Iterate through scenarios
   - Call `FKPinnClient.create_simulation()` for each scenario
   - Store returned simulation IDs for tracking

3. **Status Polling** (`src/fk_quant_research_accel/orchestrator.py:79-84`)
   - For each submitted job, call `FKPinnClient.wait_until_terminal()`
   - Polls `/api/v1/simulations/{id}` at configurable interval

4. **Result Collection** (`src/fk_quant_research_accel/orchestrator.py:85-102`)
   - Fetch final results via `FKPinnClient.get_result()`
   - Extract metrics (loss, val_loss, lr, grad_norm)
   - Compute score using `compute_score()` function
   - Create normalized record with scenario parameters and metrics

5. **Output Generation** (`src/fk_quant_research_accel/reporting.py:27-40`)
   - Write all records to CSV file
   - Create parent directories if needed
   - Use all dictionary keys as column headers

## Configuration Management

**CLI Arguments:**
- `--base-url` (required) - Base URL of FK PINN backend service
- `--dimensions` - Comma-separated integer dimensions (default: 5,10)
- `--volatilities` - Comma-separated float volatility values (default: 0.15,0.2)
- `--correlations` - Comma-separated float correlation values (default: 0.0,0.3)
- `--option-types` - Comma-separated option types (default: call)
- `--n-steps` - Training steps (default: 40)
- `--batch-size` - Batch size for training (default: 64)
- `--n-mc-paths` - Monte Carlo paths (default: 256)
- `--learning-rate` - Learning rate (default: 1e-3)
- `--poll-seconds` - Polling interval in seconds (default: 1.5)
- `--max-wait-seconds` - Maximum wait time in seconds (default: 1800)
- `--output` - Output CSV path (default: artifacts/batch_results.csv)

## Output & Storage

**CSV Output:**
- Location: `artifacts/` directory (created on demand)
- Format: CSV with headers from record dictionary keys
- Fields: simulation_id, status, dim, volatility, correlation, option_type, progress, train_loss, val_loss, lr, grad_norm, score
- Location written via `src/fk_quant_research_accel/reporting.py:27-40`

## Webhooks & Callbacks

**Incoming:** None

**Outgoing:** None

---

*Integration audit: 2026-02-19*
