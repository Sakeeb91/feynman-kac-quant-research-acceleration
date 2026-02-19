# Pitfalls Research

**Domain:** ML experiment management / research acceleration platform for PINN-based quant experiments
**Researched:** 2026-02-19
**Confidence:** HIGH (domain-specific, verified across multiple sources and codebase analysis)

---

## Critical Pitfalls

### Pitfall 1: Polling-Based Orchestration Silently Loses Long-Running Experiments

**What goes wrong:**
The current `wait_until_terminal()` loop in `client.py` (lines 55-68) uses `time.sleep()` polling with a hard 30-minute timeout. When PINN training jobs run 1-4 hours (common for high-dimensional Black-Scholes with dim > 10), the orchestrator times out and raises `TimeoutError`. The entire batch run fails, losing results from already-completed scenarios because `run_batch()` in `orchestrator.py` collects results sequentially -- a timeout on scenario N discards results from scenarios 1 through N-1 that already finished.

**Why it happens:**
Polling-based orchestration is the simplest pattern to implement and works fine for short jobs. Developers set "generous" timeouts (30 minutes feels long) without profiling actual PINN convergence times. The sequential collect loop means one failure poisons the entire batch.

**How to avoid:**
- Decouple submission from collection. Submit all jobs, then collect results independently with per-job error isolation. A failed or timed-out job should not prevent harvesting completed results.
- Persist submitted job IDs to disk (or SQLite) immediately after submission. If the orchestrator process crashes, you can resume collection without resubmitting.
- Replace fixed timeouts with adaptive deadlines based on historical run durations per scenario configuration. Store median/p95 runtimes and use `p95 * 1.5` as the timeout.
- Move toward event-driven notification (webhook or SSE from the FK PINN backend) rather than polling. Polling wastes CPU cycles and creates N * poll_interval latency for N jobs.

**Warning signs:**
- `TimeoutError` exceptions in batch runs, especially for higher-dimensional scenarios
- Batch results CSV has fewer rows than expected scenarios
- Increasing `--max-wait-seconds` keeps needing to go higher as you test harder problems
- CPU usage stays constant during "waiting" phases (polling overhead)

**Phase to address:**
Phase 1 (Durable Execution) -- this is the foundational infrastructure that everything else depends on. Without crash-resilient orchestration, no downstream feature (artifact management, reproducibility) is trustworthy.

---

### Pitfall 2: Incomplete Reproducibility Metadata Makes Experiments Unrepeatable

**What goes wrong:**
The current system captures scenario parameters (dim, volatility, correlation, option_type) and training config (n_steps, batch_size, n_mc_paths, learning_rate) but omits critical reproducibility metadata:
- No random seed capture or control
- No floating-point precision recording (FP32 vs FP64 -- this is catastrophic for PINNs, see below)
- No environment snapshot (Python version, PyTorch/JAX version, CUDA version, OS)
- No git commit SHA of the FK PINN backend being called
- No hardware identifier (CPU vs GPU, GPU model)
- No timestamp on individual job submissions or completions

Recent research (arXiv:2505.10949) demonstrates that FP32 vs FP64 is not a minor detail for PINNs -- it is a *primary failure mode*. With FP32, L-BFGS optimizers prematurely satisfy convergence tests because the tolerance (1e-7) approaches FP32's machine epsilon (1.19e-7). This causes PINNs to freeze in a "failure phase" and never converge. The same configuration in FP64 converges successfully. Without recording precision, you cannot diagnose why two "identical" runs produce different results.

**Why it happens:**
Researchers treat reproducibility metadata as "nice to have" rather than structurally required. The current `Scenario` and `BatchConfig` dataclasses capture what the researcher *intentionally varies* but not the implicit environment that affects outcomes. This is the "curse of knowledge" -- the researcher knows they are using FP64 on their machine, so they do not think to record it.

**How to avoid:**
- Define a `RunManifest` schema that is *required* before any job submission. It must include: scenario params, training config, random seed, precision dtype, environment fingerprint (Python + framework versions), git SHA of both the orchestrator and the backend, hardware identifier, and wall-clock timestamps.
- Auto-capture environment metadata at submission time. Do not rely on the researcher to manually specify it.
- Make the manifest the primary key for experiment identity. Two runs with different environments are different experiments, even if the scenario parameters match.
- Store manifests as immutable JSON alongside results. Never overwrite.

**Warning signs:**
- Two runs with "identical" parameters produce different loss values
- Cannot explain why a result from last week cannot be reproduced this week
- Results differ across machines (laptop vs workstation) with no recorded reason
- Backend was updated between runs but no version was captured

**Phase to address:**
Phase 2 (Versioned Manifests / Reproducibility) -- but the schema design should be finalized in Phase 1 planning so that the durable execution layer stores the right metadata from day one.

---

### Pitfall 3: Naive Scoring Hides Real Convergence Quality

**What goes wrong:**
The current `compute_score()` in `reporting.py` uses `train_loss + abs(grad_norm) * 0.01` as the composite score. This has multiple failure modes:
1. **Train loss is not convergence quality.** A PINN can achieve low train loss while completely failing to satisfy the PDE constraints (the "physics capture failure" documented in SciPy proceedings). The PDE residual, boundary condition error, and initial condition error must be tracked separately.
2. **The 0.01 gradient penalty weight is arbitrary.** There is no justification for this constant. In practice, gradient norms vary by orders of magnitude depending on problem dimension and learning rate. A fixed weight either over-penalizes (killing valid runs with large but stable gradients) or under-penalizes (ignoring gradient explosion).
3. **No validation loss.** The code extracts `val_loss` from metrics but never uses it in scoring. Overfitting to collocation points is a known PINN failure mode.
4. **Binary status check.** `status != "completed"` returns infinity, treating all failures equally. A run that diverged at step 2 and a run that was 99% complete but hit a transient timeout are scored identically.

**Why it happens:**
Composite scores feel like progress -- you get a single number to sort by. But researchers design the score based on what is easy to compute, not what matters for the physics. PINN-specific failure modes (stiff loss landscapes, competing PDE terms with different magnitudes) require domain-specific metrics.

**How to avoid:**
- Decompose metrics: track PDE residual loss, boundary loss, initial condition loss, and data fit loss separately. Store all of them. Let the researcher compose scores from these components.
- Replace the fixed gradient penalty with a stability metric: gradient norm variance over the last K steps, or a boolean "gradient exploded" flag.
- Include `val_loss` in the default score. For PINNs, validation on held-out collocation points detects overfitting to training points.
- Implement a multi-objective ranking (Pareto front) rather than a single scalar score. PINN quality has inherent trade-offs between accuracy, stability, and convergence speed.
- Add a "partial credit" system for runs that progressed significantly before failure.

**Warning signs:**
- Leaderboard top results have low train_loss but poor PDE residual when checked manually
- Ranking changes dramatically when you adjust the 0.01 constant
- Researchers stop trusting the score and manually inspect results anyway
- Two runs with very different convergence behaviors get similar scores

**Phase to address:**
Phase 2 or 3 (Scoring / Metrics Overhaul) -- can be designed in parallel with manifest work. The scoring system should be pluggable so researchers can define custom scoring functions without modifying core code.

---

### Pitfall 4: In-Memory State Creates an Invisible Data Loss Boundary

**What goes wrong:**
The current `run_batch()` function holds all state in Python lists (`submitted`, `records`). If the process is killed (Ctrl-C, OOM, SSH disconnect, laptop sleep), all intermediate results vanish. There is no checkpoint, no WAL, no partial recovery. For a batch of 16 scenarios where each takes 30+ minutes, losing the process at scenario 15 means losing 7+ hours of compute.

This is worse than it appears because PINN researchers often run batches overnight or over weekends. A crash at 3 AM means you discover the loss at 9 AM and have to restart from scratch.

**Why it happens:**
In-memory state is the default in Python. Adding persistence requires choosing a storage backend, designing a schema, handling concurrent access, and managing cleanup. For a prototype, the friction is not worth it. But the prototype becomes the production system.

**How to avoid:**
- Implement write-ahead logging: persist each job submission and each result collection to SQLite immediately as it happens. The in-memory list becomes a view over the durable store.
- Use atomic writes: write to a temp file, then rename. This prevents partial writes from corrupting the database on crash.
- On startup, check for incomplete batches and offer to resume them rather than starting fresh.
- Design the state schema to be append-only. Never update a row; insert a new row with a status change. This makes the history recoverable and auditable.

**Warning signs:**
- Researcher has to re-run batches after interruptions
- No way to answer "what happened to the batch I started yesterday?"
- Results directory has partial CSV files from crashed runs
- Researcher develops habit of running smaller batches "just in case"

**Phase to address:**
Phase 1 (Durable Execution) -- this is prerequisite to everything. Artifact management, reproducibility, and scoring all depend on having a reliable state store.

---

### Pitfall 5: FP32/FP64 Precision Blindness in PINN Experiments

**What goes wrong:**
This deserves its own pitfall because it is PINN-specific and not well-known outside the PDE numerics community. Research from 2025 (arXiv:2505.10949) demonstrates conclusively that many PINN "failure modes" previously attributed to loss landscape pathology are actually caused by insufficient arithmetic precision.

The mechanism: L-BFGS (the most common PINN optimizer) uses a convergence test that compares gradient magnitudes against a tolerance. In FP32, the tolerance (typically 1e-7) is at the boundary of representable precision (machine epsilon = 1.19e-7). This causes the optimizer to declare convergence while the model is still in a "failure phase" -- a transient state where the PINN has learned a spurious solution. In FP64, the same optimization continues past this phase and reaches the true solution.

The consequence for experiment management: if you do not record and control precision, your leaderboard mixes FP32 runs (which may appear converged but are actually stuck) with FP64 runs (which genuinely converged). Comparisons become meaningless.

**Why it happens:**
Most ML frameworks default to FP32. Researchers coming from deep learning backgrounds assume FP32 is sufficient (it usually is for classification/regression). The PINN community only recently identified precision as a primary variable rather than an implementation detail.

**How to avoid:**
- Make `dtype` (FP32/FP64) a first-class parameter in `Scenario` or `BatchConfig`. It must be explicitly specified, not implicitly inherited from the framework default.
- Record the actual precision used by the backend in the result manifest, not just what was requested. Verify they match.
- Default to FP64 for PINN experiments unless the researcher explicitly opts into FP32 with acknowledgment of the risks.
- Add a convergence diagnostic: if the optimizer terminates with loss near FP32 machine epsilon, flag it as "possibly precision-limited."

**Warning signs:**
- L-BFGS converges suspiciously fast on hard problems (high dimensionality, stiff PDEs)
- Results vary dramatically between machines with different default dtypes
- Loss plateaus near 1e-7 and does not decrease further
- Convergence behavior differs between Adam (which is less precision-sensitive) and L-BFGS

**Phase to address:**
Phase 2 (Versioned Manifests) -- dtype must be in the manifest schema. Phase 3 (Scoring) should include precision-aware convergence diagnostics.

---

### Pitfall 6: Overengineering the Platform Beyond Solo Researcher Needs

**What goes wrong:**
Experiment management platforms are seductive engineering problems. It is easy to build toward multi-user, distributed, cloud-native architecture when the actual use case is a single researcher on a single machine running a few dozen experiments per week. The result: months spent building infrastructure (auth, multi-tenancy, distributed queuing, cloud storage) instead of running experiments.

The existing codebase is appropriately minimal. The danger is in the hardening phase -- adopting Temporal/Airflow/Prefect for workflow orchestration, Kubernetes for job scheduling, S3 for artifact storage, and PostgreSQL for metadata when SQLite, local files, and Python asyncio would suffice.

**Why it happens:**
"Best practices" articles describe enterprise-grade MLOps. Solo researchers read these and feel their system is inadequate without distributed tracing, container orchestration, and cloud-native storage. The ecosystem of MLOps tools is designed for teams, not individuals.

**How to avoid:**
- Set a complexity budget: every new dependency must justify itself against the alternative of "Python script + SQLite + local filesystem."
- Resist adopting MLflow/W&B/Neptune unless you are actually hitting a pain point they solve. For a solo researcher, a structured directory convention + manifest files may be sufficient.
- Use the "boring technology" principle: SQLite over PostgreSQL, local filesystem over S3, subprocess over Kubernetes, asyncio over Temporal.
- Build escape hatches, not enterprise features. Design the storage layer so it *could* be swapped to cloud storage later, but implement local-first today.

**Warning signs:**
- More time spent on infrastructure than on running experiments
- Dependencies list growing faster than feature list
- README describes architecture more than research workflow
- "I need to set up X before I can run my next experiment" (infrastructure gating research)

**Phase to address:**
All phases -- this is a continuous discipline, not a one-time fix. Every phase should pass the "is this the simplest thing that could work for one researcher?" test.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| CSV-only output (current state) | Zero dependencies, human-readable | No querying, no relationships between runs, no schema enforcement, data loss on concurrent writes | MVP only. Replace with SQLite + CSV export by Phase 1. |
| `dict[str, Any]` everywhere | Flexible, no schema to maintain | No type safety, no auto-completion, silent key typos, impossible to validate manifests | Never for manifest data. Use Pydantic or dataclasses with explicit fields. |
| Sequential polling for all jobs | Simple loop, easy to debug | O(N * avg_runtime) wall clock for N jobs, single failure blocks all subsequent results | Only when N < 5 jobs. Parallelize collection for larger batches. |
| Hardcoded score formula | Quick to implement | Researchers cannot customize scoring without editing library code, couples domain logic to infrastructure | Only in initial prototype. Make scoring pluggable by Phase 2. |
| No environment capture | Less code to maintain | Unreproducible results, impossible to diagnose cross-machine discrepancies | Never acceptable once you compare results across sessions/machines. |
| In-memory job tracking | No storage dependency | Total data loss on crash, no audit trail, no resume capability | Only for interactive/exploratory single-job runs. Never for batch. |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| FK PINN Backend API | Assuming the backend returns consistent metric keys across versions. The current code (`metrics.get("loss", metrics.get("train_loss"))`) already shows the API changed key names. | Define a response schema contract. Version the API client. Map backend response keys to canonical internal names with an explicit adapter layer. |
| FK PINN Backend API | Not handling backend restarts during long-running polls. If the backend restarts, in-flight simulations may be lost but the orchestrator keeps polling forever. | Implement a "heartbeat" check: if `get_simulation()` returns 404 for a previously submitted ID, mark it as `lost` rather than polling indefinitely. |
| SQLite (future state store) | Using SQLite in WAL mode without understanding that only one writer is allowed at a time. Concurrent batch submissions from multiple terminals will produce `SQLITE_BUSY` errors. | Use a single writer process with a command queue, or accept the single-writer constraint and document it. Do not try to make SQLite multi-writer. |
| Git (for code versioning in manifests) | Capturing `git rev-parse HEAD` but not checking for uncommitted changes. A dirty working tree means the SHA does not fully describe the code state. | Capture SHA + dirty flag + diff hash. Warn if the working tree is dirty at submission time. |
| PyTorch/JAX (backend precision) | Requesting FP64 but the backend silently falls back to FP32 due to GPU limitations or configuration. The manifest says FP64 but the actual computation was FP32. | Add a verification step: after job completion, check the backend's reported precision against the requested precision. Flag mismatches. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Polling interval too aggressive | High CPU usage during batch wait, excessive API calls to backend, potential rate limiting | Start with 5-second interval, use exponential backoff, or switch to event-driven notifications | At >50 concurrent jobs or when backend is under heavy load |
| Loading all historical results into memory for comparison | OOM on large experiment histories, slow startup | Use SQLite with indexed queries. Load only summary statistics. Paginate full result sets. | At >10,000 historical experiment records |
| Writing full model checkpoints to artifact store for every epoch | Disk fills rapidly (PINN models are small but checkpoints include optimizer state) | Store only best + last checkpoint per run. Use configurable checkpoint interval. Implement retention policy. | At >100 runs with 1000+ epochs each |
| CSV file per batch with no indexing | Scanning 500 CSV files to find "all dim=10 experiments" requires reading every file | Move to SQLite early. Keep CSV as an export format, not the primary store. | At >50 batch runs |
| Cartesian product scenario generation | `generate_black_scholes_scenarios([2,5,10,20,50], [0.1,0.15,0.2,0.25,0.3], [0.0,0.1,0.2,0.3,0.4,0.5], ["call","put"])` = 300 scenarios. At 30 min each = 6.25 days. | Implement Latin hypercube or Sobol sampling for parameter spaces. Use adaptive sampling: run coarse grid first, then refine around interesting regions. | At >4 parameter dimensions or >5 values per dimension |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing API keys or backend URLs in code or CSV artifacts | Credential exposure if artifacts are shared or committed to git | Use environment variables or a `.env` file (gitignored). Never embed credentials in manifest files. |
| No input validation on scenario parameters passed to backend | Injection attacks if backend does not sanitize (unlikely but possible), more likely: nonsensical parameter combinations causing backend crashes | Validate parameter ranges before submission. Define allowed ranges per problem type. |
| Pickle-based model serialization for artifact storage | Arbitrary code execution on deserialization. If artifacts are shared between researchers, a malicious pickle file can execute arbitrary code. | Use safetensors, ONNX, or JSON-serializable formats for model artifacts. Never unpickle untrusted artifacts. |
| No access control on local artifact directory | Any process can overwrite or delete experiment results | Use file permissions appropriately. Consider append-only artifact directories where deletion requires explicit elevated action. |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Score-only leaderboard with no drill-down | Researcher cannot understand *why* a scenario scored well or poorly. Treats the platform as a black box. | Show decomposed metrics (PDE residual, boundary error, convergence rate) alongside the composite score. Allow sorting by any individual metric. |
| No progress visibility during long batch runs | Researcher has no idea if the batch is progressing, stuck, or failed. Stares at a terminal for hours. | Implement a status dashboard: per-job progress bars, ETA estimates based on historical runtimes, live metric streaming. Even a simple `[3/16 complete, ~45 min remaining]` print statement helps. |
| All-or-nothing batch results | A single failed scenario means re-running the entire batch to get the missing result | Allow partial result retrieval and incremental batch completion. Show what succeeded and offer to retry only what failed. |
| CLI-only interface with no persistent state | Researcher must remember exact CLI arguments to reproduce a run. Arguments are lost in terminal history. | Store every invocation as a "run config" in the state store. Provide `fk run --replay <run-id>` to re-execute with identical parameters. |
| Flat CSV output with no relationship to source code or config | Researcher finds an interesting result in the CSV but cannot trace back to the exact code, config, and environment that produced it | Every result row should reference a manifest ID. The manifest links to code version, config, and environment. |

## "Looks Done But Isn't" Checklist

- [ ] **Reproducibility:** Capturing scenario parameters but missing random seeds, dtype, environment versions, and git SHA -- the run *looks* reproducible but is not.
- [ ] **Crash recovery:** Batch runs complete successfully in testing but have no recovery path when interrupted -- looks robust because it has never been interrupted during testing.
- [ ] **Scoring:** Leaderboard ranks scenarios but the score formula has not been validated against known-good results (analytical solutions for simple cases) -- looks like a valid ranking but may be wrong.
- [ ] **Artifact storage:** Results are written to CSV but there is no retention policy, no deduplication, and no cleanup -- looks organized until the artifacts directory has 10,000 files.
- [ ] **API compatibility:** Client works against current backend version but has no version negotiation -- looks compatible until the backend upgrades and changes response schemas.
- [ ] **Progress tracking:** CLI prints "Top scenarios by score" at the end but provides no feedback during the run -- looks informative but only after the fact.
- [ ] **Error handling:** `requests.get().raise_for_status()` throws on HTTP errors but the error message does not include the request parameters that caused it -- looks like error handling but is not debuggable.
- [ ] **Timeout configuration:** `max_wait_seconds=1800.0` looks generous but is not based on actual PINN convergence times for the target problem space -- looks configured but is actually a guess.
- [ ] **Manifest versioning:** Schema is designed but there is no migration strategy for when the schema changes -- looks versioned but old manifests become unreadable after schema updates.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Lost batch results (crash, no persistence) | HIGH -- hours of compute wasted | Re-run entire batch. No shortcut. Prevention is the only real strategy. |
| Unreproducible experiment | MEDIUM -- detective work + re-run | Check backend logs for actual precision/version used. Compare environment across machines. If found, re-run with corrected manifest. If not found, results are scientifically invalid. |
| Corrupt scoring leading to wrong conclusions | HIGH -- all comparisons based on old score are suspect | Re-score all historical results with corrected formula. Requires all raw metrics to be stored (not just the composite score). If only scores were stored, results must be re-run. |
| Schema migration breaks old manifests | MEDIUM -- write migration script | Define a version field in manifests from day one. Write forward-migration scripts for each schema change. Keep old manifests readable forever. |
| Backend API change breaks client | LOW -- fix adapter layer | If using adapter pattern: update the adapter. If not: update every call site in the client, which may introduce bugs. |
| Overengineered platform slowing research | MEDIUM -- simplification refactor | Identify which components are actually used. Remove unused abstractions. Collapse unnecessary layers. This is easier if the code is well-tested. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Polling loses long-running experiments | Phase 1: Durable Execution | Run a batch with simulated 2-hour jobs. Kill the process mid-batch. Verify results from completed jobs are preserved and batch can be resumed. |
| Incomplete reproducibility metadata | Phase 2: Versioned Manifests | Take a successful run manifest, move to a different machine, replay it. Verify results match within numerical tolerance. If they don't, the manifest is missing something. |
| Naive scoring hides convergence quality | Phase 2-3: Scoring Overhaul | Validate scoring against analytical solutions (e.g., 1D Black-Scholes where closed-form exists). Verify the top-scored run actually has the best PDE residual. |
| In-memory state, no crash recovery | Phase 1: Durable Execution | Simulate crash (SIGKILL) during batch execution. Verify the state store has all completed results and the batch can resume from where it stopped. |
| FP32/FP64 precision blindness | Phase 2: Versioned Manifests | Run the same scenario in FP32 and FP64. Verify the manifest records the difference. Verify the scoring system flags FP32 runs that converge suspiciously near machine epsilon. |
| Overengineering beyond solo needs | All Phases | Every dependency addition must answer: "What specific pain point does this solve that a Python script + SQLite cannot?" If no answer, reject the dependency. |
| CSV-only output at scale | Phase 1: Durable Execution | Generate 100+ batch runs. Measure time to query "all dim=10, vol=0.2 experiments sorted by score." If it takes >2 seconds, the storage backend needs upgrading. |
| Schema evolution breaks old data | Phase 2: Versioned Manifests | Add a field to the manifest schema. Verify old manifests still load. Verify new manifests include the new field. Verify queries work across both versions. |
| Cartesian explosion in scenario generation | Phase 3: Advanced Orchestration | Count scenarios before submission. If count > 50, require explicit confirmation or suggest adaptive sampling. |

## Sources

- [Experience report of physics-informed neural networks in fluid simulations: pitfalls and frustration (SciPy Proceedings)](https://proceedings.scipy.org/articles/majora-212e5952-005) -- PINN-specific failure modes, convergence ambiguity, precision issues
- [FP64 is All You Need: Rethinking Failure Modes in PINNs (arXiv:2505.10949)](https://arxiv.org/html/2505.10949v1) -- Definitive evidence that FP32 causes premature convergence in PINNs
- [Challenges in Training PINNs: A Loss Landscape Perspective (arXiv:2402.01868)](https://arxiv.org/pdf/2402.01868) -- Loss landscape complexity, local minima, competing loss terms
- [Characterizing possible failure modes in PINNs (NeurIPS 2021)](https://proceedings.neurips.cc/paper/2021/file/df438e5206f31600e6ae4af72f2725f1-Paper.pdf) -- Systematic analysis of PINN failure modes
- [ML experiment management tools: a mixed-methods empirical study (Springer, 2024)](https://link.springer.com/article/10.1007/s10664-024-10444-w) -- Adoption barriers, overengineering risks for research contexts
- [MLXP: A Framework for Conducting Replicable Experiments in Python (arXiv:2402.13831)](https://arxiv.org/html/2402.13831v2) -- Lightweight experiment management, avoiding framework lock-in
- [Building a lightweight experiment manager (Dagworks Blog)](https://blog.dagworks.io/p/building-a-lightweight-experiment) -- Practical pitfalls in experiment manager design, boilerplate overhead
- [How to Solve Reproducibility in ML (Neptune.ai)](https://neptune.ai/blog/how-to-solve-reproducibility-in-ml) -- Environment capture, metadata requirements
- [Reproducibility in ML-based Research (arXiv:2406.14325)](https://arxiv.org/html/2406.14325v1) -- Five pillars of ML reproducibility, common gaps
- [Management of ML Lifecycle Artifacts: A Survey (ACM SIGMOD, 2022)](https://dl.acm.org/doi/10.1145/3582302.3582306) -- Artifact lifecycle, cross-system reproducibility challenges
- [ML Model Packaging: The Ultimate Guide (Neptune.ai)](https://neptune.ai/blog/ml-model-packaging) -- Research-to-production handoff, dependency management
- [Durable Python: Reliable Long-Running Workflows (Autokitteh)](https://autokitteh.com/technical-blog/durable-python-reliable-long-running-workflows-with-just-a-few-lines-of-code/) -- Durable execution patterns, idempotency requirements
- [Common Pitfalls When Designing Metrics (LinkedIn DPH Framework)](https://linkedin.github.io/dph-framework/metric-pitfalls.html) -- Composite metric design mistakes, aggregate score problems
- [Auto-PINN: Understanding and Optimizing Physics-Informed Neural Architecture (arXiv:2205.13748)](https://arxiv.org/html/2205.13748) -- PINN hyperparameter sensitivity, architecture search
- [Backward Compatibility in Schema Evolution (DataExpert)](https://www.dataexpert.io/blog/backward-compatibility-schema-evolution-guide) -- Schema migration patterns, expand-contract approach

---
*Pitfalls research for: ML experiment management / PINN quant research acceleration platform*
*Researched: 2026-02-19*
