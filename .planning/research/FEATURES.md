# Feature Research

**Domain:** ML experiment management / scientific computing research acceleration (Feynman-Kac PINN solvers)
**Researched:** 2026-02-19
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete. Derived from MLflow, W&B, Neptune, DVC, Optuna, and domain-specific PINN/quant tools.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Experiment tracking with unique run IDs** | Every platform (MLflow, W&B, Neptune, Sacred) generates unique run identifiers. Without this, experiments are indistinguishable and unreferenceable. Current codebase uses simulation_id from backend but has no local run registry. | LOW | Assign UUID per batch run; link all scenario results to that run_id. Foundation for everything else. |
| **Full config capture per run** | MLflow auto-logs parameters, W&B captures hyperparams + git SHA + environment. Researchers expect to look at any past run and see exactly what was configured. Current codebase passes params but does not persist the full config snapshot. | LOW | Serialize Scenario + BatchConfig + CLI args + git SHA + Python version to JSON/YAML alongside CSV output. |
| **Reproducibility metadata** | DVC versions data + code + config. W&B logs git commit hash, Python packages, hardware info. A run without reproducibility metadata is a run you cannot repeat. Currently missing: seed tracking, env capture, code version. | MEDIUM | Capture: random seed, git SHA, pip freeze, Python version, OS, backend URL/version. Store as run manifest. |
| **Structured result schema** | All platforms normalize outputs (MLflow metrics, W&B summary). Current CSV output is flat and ad-hoc; metrics keys depend on backend response shape. Researchers expect consistent columns regardless of scenario type. | MEDIUM | Define Pydantic models for RunResult with required fields (status, losses, runtime, error_stats, score) and optional extension fields. Validate before writing. |
| **Comparison across runs** | MLflow comparison UI, W&B parallel coordinates, Neptune diff view. Comparing two batches is the whole point of experiment tracking. Current codebase ranks within a single batch but cannot compare across batches. | MEDIUM | Requires run registry (run_id + metadata index). Then: load two runs, align by scenario params, compute deltas. CLI command: `compare-runs run_id_1 run_id_2`. |
| **Configurable scoring/ranking** | Optuna supports multi-objective optimization. W&B custom metrics. Current scoring is hardcoded (train_loss + grad_norm penalty). Researchers need domain-specific criteria: convergence rate, uncertainty bounds, runtime efficiency. | MEDIUM | Scoring as pluggable strategy (protocol/ABC). Ship defaults: loss-based, convergence-rate, Pareto multi-objective. User provides custom scorer via config or Python callable. |
| **Failure handling and partial results** | MLflow marks failed runs. W&B continues logging even on crash. Current codebase loses all progress if CLI crashes mid-batch; failed simulations get score=inf with no retry. | MEDIUM | Checkpoint submitted simulation IDs to disk. On crash/restart, detect completed simulations and resume remaining. Separate failed records from successful ones in output. |
| **Declarative experiment config (YAML/JSON)** | Hydra, DVC, and MLflow Projects all use declarative config files. Current codebase uses CLI args only -- not versionable, not diffable, not shareable. Researchers expect to commit experiment definitions to git. | LOW | YAML manifest defining scenario grid + batch config + scoring strategy + output paths. CLI reads manifest: `run-batch --manifest experiments/vol_sweep_v3.yaml`. |
| **Artifact organization** | MLflow artifacts, W&B file logging, DVC tracked outputs. Current codebase writes a single CSV to a user-specified path. No directory structure, no artifact metadata, no linkage to run_id. | LOW | `artifacts/{run_id}/` directory containing: manifest.yaml, results.csv, metadata.json, score_summary.json. Symlink `artifacts/latest` to most recent run. |
| **Logging and observability** | Every production-quality tool provides structured logging. Current codebase uses print() for top-10 display only. No visibility into submission progress, poll attempts, failures. | LOW | Python `logging` module with configurable levels. Log: scenario submission, poll attempts, completion, failures, timing. `--log-level` CLI flag. |

### Differentiators (Competitive Advantage)

Features that set the product apart from generic ML experiment trackers. Specific to the FK PINN + quant research acceleration domain.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Concurrent async batch execution** | W&B sweeps and Ray Tune parallelize across workers. Current codebase polls simulations sequentially -- a 100-scenario batch that could finish in 30 minutes takes 50+ hours. The "walk away and come back" promise requires concurrent polling. This is the single highest-impact feature for research throughput. | MEDIUM | Use `asyncio` or `concurrent.futures.ThreadPoolExecutor` to poll all submitted simulations concurrently. Cap concurrent connections (e.g., 10-20). Expected speedup: 10-50x for batches >10 scenarios. |
| **Model packaging for winning runs** | MLflow model packaging and registry. No generic tracker packages PINN checkpoints with PDE config + validation summary + deployment metadata. This bridges the gap from "research artifact" to "deployable model." | HIGH | Export: model checkpoint (weights), scenario config, training config, validation metrics, convergence plot data, environment spec. Format: directory with manifest + checkpoint + config + validation_summary.json. |
| **Domain-specific statistical validation gates** | QuantConnect validates with walk-forward windows, Sharpe ratios, drawdown limits. Generic trackers log metrics but don't enforce acceptance criteria. PINN-specific validation: PDE residual convergence, boundary condition satisfaction, Monte Carlo error bounds, solution smoothness. | HIGH | Define validation protocol: (1) PDE residual norm < threshold, (2) boundary error < threshold, (3) MC variance within bounds, (4) gradient stability check. Configurable thresholds per problem type. Gate output: pass/fail/warn per criterion. |
| **Scenario grid DSL with constraints** | Optuna defines search spaces programmatically. Generic grid search is Cartesian product (current approach). Domain-specific: constrain correlation matrices to be positive-definite, enforce volatility smile consistency, filter infeasible parameter combinations before submission. | MEDIUM | Extend YAML manifest with `constraints:` section. Built-in validators: positive-definite correlation, sensible vol ranges, dim-compatible option types. Pre-flight check before batch submission. Reject invalid combos with clear error. |
| **Convergence diagnostics beyond final loss** | W&B logs training curves. But PINN convergence has domain-specific failure modes: oscillating loss, gradient explosion in high dimensions, boundary condition drift. Automated detection of these patterns saves hours of manual curve inspection. | MEDIUM | Analyze training trajectory (not just terminal metrics): detect oscillation (loss variance in last N steps), gradient explosion (grad_norm trend), stagnation (loss plateau detection). Report per-scenario convergence health: healthy/oscillating/stagnating/exploding. |
| **Run comparison with statistical significance** | Neptune and W&B show metric diffs but leave statistical interpretation to the user. For quant research: are two architectures actually different, or is the difference within noise? Automated significance testing on batch results. | MEDIUM | For matched scenario pairs across two runs: paired t-test or Wilcoxon signed-rank on loss/score. Report: mean improvement, p-value, effect size. Prevents cherry-picking and publication bias in internal research. |
| **Incremental/streaming result capture** | DVC pipelines re-run only changed stages. Current codebase writes CSV once at end -- crash loses everything. Stream results to disk as each simulation completes. | LOW | Write each completed scenario result to CSV immediately (append mode). Maintain in-memory sorted view for ranking. On crash, resume from disk checkpoint. |
| **Problem-type extensibility** | DeepXDE supports multiple PDE types, NVIDIA Modulus supports various physics. Current codebase hardcodes `black_scholes`. Researchers need to add new problem types (heat equation, portfolio optimization) without modifying orchestrator internals. | MEDIUM | Problem type as a pluggable module: `ProblemSpec` protocol defining parameter schema, scenario generator, scorer, and validator. Register via entry points or config. Ship with: `black_scholes`, `harmonic_oscillator`. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems. Drawn from MLOps anti-patterns research and the specific constraints of this project (solo researcher, local-first, v1 scope).

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Web dashboard / GUI** | MLflow, W&B, Neptune all have web UIs. Seems essential for visualization. | For a solo researcher running local experiments, a web server adds deployment complexity, security surface, and maintenance burden. The researcher is already in a terminal + notebook workflow. Building a web app is a multi-week detour from research acceleration. | CLI summary output + CSV/JSON artifacts that load instantly into Jupyter/pandas. Optionally generate static HTML reports (single file, no server). Defer dashboard to v2 if demand proves real. |
| **Real-time training metric streaming** | W&B streams metrics live. Looks impressive in demos. | Requires websocket/SSE infrastructure, frontend rendering, and changes to the FK PINN backend API contract. The backend uses polling, not push. Real-time adds complexity for marginal value when batch runs are unattended ("walk away and come back"). | Polling-based progress snapshots written to disk at configurable intervals. Researcher can `tail -f` or check periodically. Sufficient for solo unattended use. |
| **Multi-user collaboration features** | W&B teams, MLflow sharing, Neptune workspaces. | Solo researcher use case. Multi-user adds auth, permissions, conflict resolution, shared state. All complexity, zero value for v1. | Git-based sharing: commit experiment manifests + artifacts to repo. Collaboration via PR review of experiment configs and results. Natural for solo→small-team transition. |
| **Cloud/distributed execution** | Ray, Spark, Kubernetes for scaling. | Requires infrastructure provisioning, networking, credential management, distributed state. The FK PINN backend runs locally. Adding cloud compute before the local workflow is solid creates two problems instead of solving one. | Optimize local throughput first (concurrent polling, batch queuing). Support multiple local backends via `--base-urls` round-robin. Cloud is v2+ after local patterns are proven. |
| **Auto-ML / neural architecture search** | Optuna, Ray Tune, Auto-sklearn automate model selection. | PINN architecture is constrained by physics (boundary conditions, PDE structure). Auto-ML over neural architectures ignores domain constraints and produces nonsensical configurations. The researcher's judgment on architecture is the valuable input; the platform automates the boring parts (submission, tracking, comparison). | Support architecture as a sweep dimension (e.g., `architectures: [fnn_3x64, resnet_4x128]`) but let the researcher define the candidates. Never auto-generate architectures without domain constraints. |
| **Comprehensive model registry with stages** | MLflow model registry has "Staging", "Production", "Archived" stages. | Stage transitions imply a deployment pipeline that does not exist in v1. Adding registry stages before there is a serving endpoint creates ceremony without value. The researcher needs to find the best model, not manage a deployment lifecycle. | Simple model packaging: winning run exports to `packages/{run_id}/` with checkpoint + config + validation summary. Tag as "best" via symlink or manifest entry. Full registry is v2 when serving endpoint exists. |
| **Plugin marketplace / extension system** | Extensible platforms attract ecosystems. | Solo researcher does not need an ecosystem. Extension systems require stable APIs, documentation, versioning. Building the extension system takes longer than building the extensions. | Direct Python extensibility: custom scorers as callables, custom validators as functions. If the researcher can write a Python function, they can extend the platform. No plugin API needed. |
| **Notebook-native experiment definition** | Sacred runs from notebooks, W&B integrates with Jupyter. | Notebook state is the root cause of the reproducibility problem this platform solves. Notebook-first experiment definition reintroduces the exact pain point: invisible state, non-diffable config, execution order ambiguity. | YAML manifests committed to git for experiment definition. Notebooks for analysis of results (reading CSV/JSON artifacts). Clear separation: define experiments in config, analyze results in notebooks. |

## Feature Dependencies

```
[Experiment Run IDs]
    |
    +--requires--> [Artifact Organization]
    |                  |
    |                  +--requires--> [Model Packaging]
    |
    +--requires--> [Full Config Capture]
    |                  |
    |                  +--requires--> [Reproducibility Metadata]
    |                  |
    |                  +--enhances--> [YAML Experiment Manifests]
    |
    +--requires--> [Structured Result Schema]
    |                  |
    |                  +--enhances--> [Configurable Scoring]
    |                  |
    |                  +--enhances--> [Cross-Run Comparison]
    |                  |                   |
    |                  |                   +--enhances--> [Statistical Significance Testing]
    |                  |
    |                  +--enhances--> [Convergence Diagnostics]
    |
    +--enhances--> [Failure Handling / Partial Results]
                       |
                       +--enhances--> [Incremental Result Capture]

[YAML Experiment Manifests]
    |
    +--enhances--> [Scenario Grid DSL with Constraints]

[Concurrent Async Execution]
    |
    +--independent (no hard dependencies, but requires Failure Handling for robustness)

[Logging/Observability]
    |
    +--independent (enhances everything, blocks nothing)

[Problem-Type Extensibility]
    |
    +--requires--> [Structured Result Schema]
    +--requires--> [Configurable Scoring]
    +--requires--> [YAML Experiment Manifests]
```

### Dependency Notes

- **Run IDs require Artifact Organization:** Without a directory structure keyed by run_id, there is nowhere to persist run metadata. These two features must ship together.
- **Config Capture requires nothing but enables everything:** Capturing full config is the foundation of reproducibility. Low complexity, high leverage. Ship first.
- **Structured Result Schema enables Scoring + Comparison + Diagnostics:** All downstream analysis features depend on normalized, validated result data. Schema must be stable before building comparison or diagnostics.
- **Cross-Run Comparison requires Run Registry:** Cannot compare runs if you cannot enumerate and load past runs. Run registry (index of run_ids + metadata) is the prerequisite.
- **Model Packaging requires Artifact Organization:** Packaging writes checkpoint + config + validation to a structured directory. Needs the artifact layout to exist.
- **Problem-Type Extensibility requires Schema + Scoring + Manifests:** Extensibility is a cross-cutting concern that touches scenario generation, result validation, and scoring. Only feasible after core abstractions are stable.
- **Concurrent Execution is independent but fragile without Failure Handling:** Can be built in isolation, but without crash recovery, a concurrent batch that fails loses more work than a sequential one. Ship failure handling alongside or before concurrency.

## MVP Definition

### Launch With (v1.0)

Minimum viable product -- sufficient for a researcher to define a batch, walk away, and come back to ranked, reproducible results.

- [x] Scenario generation via Cartesian product (existing)
- [x] HTTP client with polling (existing)
- [x] Batch orchestration: submit + poll + collect (existing)
- [x] CSV export with scoring (existing)
- [ ] **Experiment run IDs + artifact directory** -- Without this, runs are unnamed blobs. Foundation for everything.
- [ ] **Full config capture per run** -- Serialize all inputs (scenario grid, batch config, CLI args, git SHA, seed) to `artifacts/{run_id}/manifest.yaml`.
- [ ] **YAML experiment manifests** -- Move experiment definition from CLI args to versionable config files. Solves the "notebook state" reproducibility problem.
- [ ] **Structured result schema** -- Pydantic models for RunResult. Validate before writing. Consistent columns regardless of backend quirks.
- [ ] **Logging and observability** -- Replace print() with structured logging. `--log-level` flag. Log all lifecycle events.
- [ ] **Failure handling + incremental writes** -- Checkpoint simulation IDs to disk. Resume on crash. Write results as they complete.
- [ ] **Concurrent async batch execution** -- The highest-impact throughput feature. Without this, the "walk away" promise is broken for batches >10 scenarios.

### Add After Validation (v1.x)

Features to add once core workflow is proven with real research batches.

- [ ] **Configurable scoring/ranking** -- When researchers need custom metrics beyond loss + grad_norm. Trigger: researcher manually post-processes CSV to compute custom scores.
- [ ] **Cross-run comparison** -- When the researcher accumulates 5+ batch runs and needs to compare architectures or parameter regimes systematically.
- [ ] **Convergence diagnostics** -- When the researcher spends >30 minutes manually inspecting training curves for failure patterns.
- [ ] **Scenario grid DSL with constraints** -- When invalid parameter combinations waste significant compute (e.g., non-positive-definite correlation matrices submitted and failed).
- [ ] **Reproducibility metadata (full env capture)** -- When reproducing a past run fails because of environment drift.
- [ ] **Problem-type extensibility** -- When the researcher needs to run non-Black-Scholes problems through the same pipeline.

### Future Consideration (v2+)

Features to defer until the research workflow is solid and serving/deployment becomes the bottleneck.

- [ ] **Model packaging** -- Requires serving endpoint to consume the package. Until v2 serving exists, the researcher can manually export winning checkpoints.
- [ ] **Statistical significance testing** -- Valuable but requires enough runs to be meaningful. Defer until comparison workflow is proven.
- [ ] **Domain-specific validation gates** -- Requires deep PDE-specific validation logic. Defer until scoring and diagnostics prove the need.
- [ ] **Web dashboard** -- Only if CLI + notebook analysis proves insufficient for the solo researcher.
- [ ] **Model registry with lifecycle stages** -- Only when serving endpoint (v2) creates demand for stage transitions.
- [ ] **Multi-backend distribution** -- Only when local throughput is maxed out.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Concurrent async execution | HIGH | MEDIUM | P1 |
| Experiment run IDs + artifact dirs | HIGH | LOW | P1 |
| Full config capture per run | HIGH | LOW | P1 |
| YAML experiment manifests | HIGH | LOW | P1 |
| Structured result schema | HIGH | MEDIUM | P1 |
| Failure handling + incremental writes | HIGH | MEDIUM | P1 |
| Logging and observability | MEDIUM | LOW | P1 |
| Configurable scoring/ranking | HIGH | MEDIUM | P2 |
| Cross-run comparison | HIGH | MEDIUM | P2 |
| Convergence diagnostics | MEDIUM | MEDIUM | P2 |
| Scenario grid DSL with constraints | MEDIUM | MEDIUM | P2 |
| Reproducibility metadata (full) | MEDIUM | LOW | P2 |
| Problem-type extensibility | MEDIUM | HIGH | P2 |
| Model packaging | HIGH | HIGH | P3 |
| Statistical significance testing | MEDIUM | MEDIUM | P3 |
| Domain-specific validation gates | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Must have for launch -- the core "define, run, rank, reproduce" loop
- P2: Should have, add when P1 is proven with real research batches
- P3: Nice to have, future consideration (v2+ or when clear demand emerges)

## Competitor Feature Analysis

| Feature | MLflow | W&B | Optuna | DVC | Sacred | This Platform |
|---------|--------|-----|--------|-----|--------|---------------|
| Experiment tracking | Full (run IDs, params, metrics, artifacts) | Full + auto-logging | Via integrations (MLflow, W&B) | Git-based experiment tracking | Config + metric logging | **Build: run IDs + config capture + structured results** |
| Reproducibility | Code versioning, env capture | Git SHA, pip freeze, hardware | N/A (optimization only) | Full pipeline + data versioning | Auto-captures dependencies | **Build: manifest + git SHA + seed + env snapshot** |
| Hyperparameter sweeps | Grid/random via Projects | Bayesian, grid, random sweeps | Core strength: TPE, GP, CMA-ES | Via Hydra integration | N/A | **Build: scenario grid (Cartesian + constraints). Defer: smart search (Bayesian).** |
| Parallel execution | Via Spark/distributed backends | Sweep agents on multiple machines | Distributed via storage backend | Pipeline parallelism | N/A | **Build: concurrent async polling. Defer: multi-machine.** |
| Model packaging | MLflow Model format (standard) | Artifact logging | N/A | DVC-tracked model files | N/A | **Defer to v2: checkpoint + config + validation bundle** |
| Comparison/analysis | Comparison UI, metric plots | Parallel coordinates, custom panels | Visualization dashboard | Metrics diff via CLI | Omniboard (separate) | **Build: CLI cross-run comparison. Defer: visualization.** |
| Config management | MLflow Projects (conda.yaml) | wandb.config | Define-by-run API | dvc.yaml + Hydra | Sacred config scope | **Build: YAML manifests. Leverage: Hydra integration possible later.** |
| Domain specificity | Generic ML | Generic ML | Generic optimization | Generic ML pipelines | Generic ML | **Differentiator: PINN convergence diagnostics, PDE validation gates, quant-specific scoring** |
| Deployment target | Solo to team | Team-first (cloud) | Library (embeds in any tool) | Solo to team (git-based) | Solo researcher | **Solo researcher, local-first. Git-based sharing for team transition.** |

## Sources

- [MLflow Documentation](https://mlflow.org/docs/latest/) - Model registry, experiment tracking, model packaging features (HIGH confidence)
- [Weights & Biases Documentation](https://docs.wandb.ai/) - Sweep architecture, experiment tracking, auto-logging (HIGH confidence)
- [Optuna Documentation](https://optuna.readthedocs.io/) - Hyperparameter optimization, multi-objective, distributed studies (HIGH confidence)
- [DVC Documentation](https://doc.dvc.org/) - Data versioning, pipeline management, experiment tracking (HIGH confidence)
- [Neptune.ai Blog - Best ML Experiment Tracking Tools](https://neptune.ai/blog/best-ml-experiment-tracking-tools) - Feature comparison across 15+ tools (MEDIUM confidence)
- [Hydra Documentation](https://hydra.cc/) - Config composition, reproducibility, experiment management patterns (HIGH confidence)
- [DeepXDE GitHub](https://github.com/lululxvi/deepxde) - PINN framework feature set, multi-backend support (HIGH confidence)
- [NVIDIA PhysicsNeMo (Modulus)](https://github.com/NVIDIA/physicsnemo) - Physics ML framework, PDE solving pipeline (HIGH confidence)
- [MLOps Anti-Patterns Paper](https://arxiv.org/abs/2107.00079) - Common mistakes in ML operations, over-engineering risks (MEDIUM confidence)
- [Springer - ML Experiment Management Tools Empirical Study](https://link.springer.com/article/10.1007/s10664-024-10444-w) - Academic analysis of experiment management tool features and usage patterns (MEDIUM confidence)
- [QuantConnect](https://www.quantconnect.com/) - Quant research platform features: parameter sensitivity, walk-forward validation (MEDIUM confidence)

---
*Feature research for: ML experiment management / FK PINN quant research acceleration*
*Researched: 2026-02-19*
