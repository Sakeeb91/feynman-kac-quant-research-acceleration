# Feynman-Kac Quant Research Acceleration Platform

## What This Is

A research acceleration platform built on Feynman-Kac PINN solvers. Researchers define versioned scenario grids (PDE parameter sweeps, model/architecture comparisons, seed replication), run asynchronous batch experiments, and get standardized outputs: convergence metrics, uncertainty estimates, runtime, and ranked leaderboards. Winning models are exported as reproducible, deployable packages.

## Core Value

A researcher can define a 50-200 scenario batch, walk away, and come back to a ranked leaderboard with full reproducibility metadata and a deployable model package for the winner.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. Inferred from existing codebase. -->

- Scenario generation via Cartesian product of PDE parameters (dim, volatility, correlation, option_type) -- existing
- Immutable scenario/config data classes (frozen dataclasses) for reproducibility -- existing
- HTTP client for FK PINN backend with polling and timeout handling -- existing
- Batch orchestration: submit scenarios, poll status, collect results -- existing
- Composite scoring function (train_loss + gradient norm penalty, failed runs penalized) -- existing
- CSV export of ranked results to artifacts/ -- existing
- CLI entry point for batch runs with argument parsing -- existing
- CI pipeline (GitHub Actions: lint, type-check, test) -- existing

### Active

<!-- Current scope. Building toward these. -->

- [ ] Versioned scenario manifests (YAML/JSON config files, not notebook state)
- [ ] Durable async execution with failure recovery and restart survival
- [ ] Standardized output schema (status, losses, runtime, uncertainty/error stats, rank score)
- [ ] Full reproducibility from run_id (config, seed, code SHA, environment metadata)
- [ ] Model packaging for winning runs (checkpoint + config + metadata + validation summary)
- [ ] Domain-specific ranking/scoring with configurable acceptance criteria
- [ ] Unattended batch execution for 50-200 scenario studies
- [ ] Model comparison axis support (architecture, optimizer/scheduler sweeps alongside PDE sweeps)

### Out of Scope

<!-- Explicit boundaries. -->

- Serving/inference endpoint for deployed models -- v2 (productization, not needed for research)
- Cloud/distributed execution infrastructure -- v1 is local-first
- Web UI/dashboard -- CLI and programmatic API are sufficient for solo researcher
- Multi-user collaboration features -- solo use case for v1
- Real-time streaming of training metrics -- polling-based approach is sufficient

## Context

**Existing codebase (brownfield):** ~65% solid foundation, ~35% platform hardening needed.

**Solid and reusable:**
- Problem abstractions in `feynman-kac-pinn/ml/problems` (Black-Scholes, harmonic oscillator, registry pattern)
- Monte Carlo core in `feynman-kac-pinn/ml/data/brownian.py` and `ml/utils/mc_estimator.py` (variance reduction, adaptive sampling)
- Training baseline in `feynman-kac-pinn/ml/training/trainer.py` (checkpointing, schedulers, clipping, early-stop)
- API contracts in `feynman-kac-pinn/backend/app/api/routes` shaped for platform integration
- Layered client-orchestrator architecture in this repo (client, orchestrator, reporting, CLI)

**Needs rethinking:**
- `simulation_manager.py` is in-memory orchestration; needs durable queue/state, retries, worker isolation
- No artifact lifecycle: no model registry or versioned checkpoint metadata tied to experiment IDs
- Reproducibility metadata incomplete: seed, env, git SHA, manifest tracking not first-class
- Ranking logic intentionally simple; needs domain-specific scoring with configurable criteria
- Validation is smoke-level; needs stronger statistical/numerical gates

**Current pain being solved:**
1. Manual bookkeeping failure -- configs scattered in notebooks, failed runs dropped silently
2. Reproducibility failure -- config in notebook state, inconsistent seeds, no audit trail
3. Sequential bottleneck -- runs launched one-by-one, all-day babysitting for 30-50 scenarios
4. Comparison/decision failure -- unnormalized outputs, subjective ranking, cherry-picked screenshots

**Production handoff pipeline (staged):**
1. Research artifact (v1) -- reproducible ranked outputs
2. Model package (v1) -- checkpoint + config + metadata + validation summary
3. Service deployment (v2) -- inference endpoint for live/batch pricing

## Constraints

- **Local-first**: Must run on a single machine without cloud infrastructure dependency for v1
- **Existing solver APIs**: Must preserve the current feynman-kac-pinn solver interface contracts
- **Python-first**: Primary language is Python; non-Python layers acceptable if needed later
- **Python 3.10+**: Minimum runtime version per existing project configuration

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Build on existing layered architecture (client/orchestrator/reporting/CLI) | 65% solid foundation, avoid rewrite risk | -- Pending |
| YAML manifests for scenario definitions | Human-readable, versionable, diffable configs | -- Pending |
| Local-first execution for v1 | Removes infra dependency, usable immediately for real research | -- Pending |
| v1 boundary = grid + async + ranking + model packaging | Sufficient for real research; serving layer deferred to v2 | -- Pending |
| Preserve FK PINN solver interface | Strongest asset in the stack; avoid unnecessary rewrite risk | -- Pending |

---
*Last updated: 2026-02-19 after initialization*
