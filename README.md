# Feynman-Kac Quant Research Acceleration

A research orchestration layer for running large, repeatable quant experiments on top of the
[Feynman-Kac PINN](https://github.com/Sakeeb91/feynman-kac-pinn) simulation API.

This repository is focused on **research throughput** rather than PDE implementation details.
It provides a batch-experiment workflow for:

- high-dimensional Black-Scholes scenario sweeps,
- asynchronous job submission and tracking,
- normalized result capture, and
- leaderboard-style comparison of convergence/runtime quality.

## Why This Exists

Quant teams lose time when every hypothesis test requires bespoke scripts, ad-hoc notebooks,
and manual result aggregation. This project standardizes that loop:

1. define a scenario grid,
2. submit jobs to a Feynman-Kac PINN service,
3. collect outputs into consistent artifacts,
4. rank experiments by risk/performance metrics.

## Architecture

- `fk_quant_research_accel.client.FKPinnClient`:
  typed client for `/api/v1/problems`, `/api/v1/simulations`, and `/api/v1/results`.
- `fk_quant_research_accel.orchestrator`:
  scenario generation + asynchronous batch execution.
- `fk_quant_research_accel.reporting`:
  CSV writing, score computation, and leaderboard sorting.
- `fk_quant_research_accel.cli`:
  command-line runner for reproducible experiment batches.

## Quick Start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Run Against a Local FK PINN Backend

Start the backend in the original FK PINN repository:

```bash
cd "/Users/sakeeb/Code repositories/feynman-kac-pinn/backend"
uvicorn app.main:app --reload
```

In this repo:

```bash
python -m fk_quant_research_accel.cli run-batch \
  --base-url http://127.0.0.1:8000 \
  --dimensions 5,10 \
  --volatilities 0.15,0.2 \
  --correlations 0.0,0.3 \
  --output artifacts/black_scholes_batch.csv
```

### 3. Output

The CLI writes a normalized CSV with per-scenario records:

- scenario parameters,
- simulation lifecycle status,
- progress and terminal metrics,
- scalar score for ranking experiments.

## Typical Use Cases

- intraday model version comparison,
- parameter-stability studies under volatility/correlation shifts,
- benchmark packs for candidate architecture changes,
- pre-release regression checks for quant research pipelines.

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## License

MIT
