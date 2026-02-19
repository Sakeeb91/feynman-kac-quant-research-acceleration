# Stack Research

**Domain:** Local-first Python experiment management platform for ML/scientific computing (quant research acceleration)
**Researched:** 2026-02-19
**Confidence:** HIGH (core libraries verified via Context7 + PyPI; versions confirmed via web search)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| Python | >=3.11 | Runtime | 3.11+ gives native `asyncio.TaskGroup` for structured concurrency. 3.10 minimum in existing `pyproject.toml` should bump to 3.11 for async task group support without third-party dependency. 3.12 improves error messages and GC. | HIGH |
| Pydantic | >=2.12.5 | Config validation, manifest schemas, result models | Replaces frozen dataclasses with validated, serializable models. `model_config = dict(frozen=True)` preserves immutability. JSON Schema generation gives free manifest validation. Rust core (pydantic-core) makes validation fast. The existing frozen dataclasses (`Scenario`, `BatchConfig`) migrate trivially. | HIGH |
| pydantic-settings | >=2.13.0 | Environment/runtime configuration | Loads from env vars, `.env` files, YAML, and CLI. Separates "what to run" (manifest) from "where to run" (runtime settings like base_url, poll intervals). | HIGH |
| AnyIO | >=4.12.1 | Structured async concurrency | Wraps asyncio with proper structured concurrency (cancel scopes, task groups). The existing `run_batch` is sequential polling -- AnyIO task groups enable concurrent scenario execution with clean cancellation. AnyIO's API is a superset of `asyncio.TaskGroup` with cancel scope control and `start_soon` with readiness signaling that asyncio still lacks. | HIGH |
| SQLite (stdlib) | 3.x (stdlib) | Experiment metadata store, run state persistence | Zero-dependency, ACID-compliant, local-first. Handles concurrent reads, survives process crashes. MLflow uses SQLite backend for local tracking for the same reasons. Sufficient for 10K+ experiment records. Already in Python stdlib. | HIGH |
| PyYAML | >=6.0.3 | Manifest file parsing | Standard YAML parser. Manifests are human-authored scenario grid definitions -- YAML is diffable, versionable, reviewable. 6.0.3 adds Python 3.14 support. | HIGH |
| Typer | >=0.21.0 | CLI framework | Replaces existing argparse CLI with type-hint-driven interface. Auto-generates help, shell completion. Built on Click. Existing CLI has ~50 lines of argparse boilerplate that Typer eliminates. | HIGH |
| Rich | >=14.2.0 | Terminal output, progress bars, tables | Leaderboard display, batch progress tracking, error formatting. Integrates with Typer. Replaces current `print()` statements with structured terminal output. | MEDIUM |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| structlog | >=25.5.0 | Structured logging | Every experiment run. JSON-formatted logs with run_id, scenario params as context. Queryable post-hoc. Structured key-value pairs map to experiment metadata naturally. | MEDIUM |
| httpx | >=0.28.0 | Async HTTP client | Replace `requests` for async scenario submission. httpx is the async-native equivalent of requests with nearly identical API. Required for concurrent batch execution. | HIGH |
| gitpython | >=3.1.44 | Git SHA capture for reproducibility | Every experiment run. Captures commit hash + dirty status for reproducibility metadata. Lightweight read-only usage. | MEDIUM |
| platformdirs | >=4.3.6 | Cross-platform artifact/config paths | Determining where to store experiments, artifacts, caches per OS conventions. | LOW |

### Development Tools

| Tool | Version | Purpose | Notes | Confidence |
|------|---------|---------|-------|------------|
| uv | >=0.10.4 | Package management + virtualenv | 10-100x faster than pip. Drop-in replacement. Handles venv creation, dependency resolution, lockfiles. From same team as Ruff. | HIGH |
| Ruff | >=0.15.1 | Linter + formatter | Already in project (`>=0.6.0`). Bump version. Replaces flake8, black, isort in one tool. | HIGH |
| mypy | >=1.19.1 | Static type checking | Already in project (`>=1.10.0`). Bump version. Critical for Pydantic model correctness. | HIGH |
| pytest | >=9.0.2 | Testing | Already in project (`>=8.0.0`). Bump version. | HIGH |
| pytest-asyncio | >=0.25.0 | Async test support | Required for testing AnyIO/async code paths. | MEDIUM |

## Installation

```bash
# Use uv instead of pip (10-100x faster)
uv pip install -e ".[dev]"

# Or traditional pip
pip install -e ".[dev]"
```

### pyproject.toml dependencies (proposed)

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.12.5",
    "pydantic-settings>=2.13.0",
    "anyio>=4.12.1",
    "httpx>=0.28.0",
    "typer>=0.21.0",
    "rich>=14.2.0",
    "PyYAML>=6.0.3",
    "structlog>=25.5.0",
    "gitpython>=3.1.44",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.0.2",
    "pytest-asyncio>=0.25.0",
    "ruff>=0.15.1",
    "mypy>=1.19.1",
]

# Optional: heavier tracking for teams that want MLflow UI
tracking = [
    "mlflow-skinny>=3.9.0",
]
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative | Why Not Default |
|-------------|-------------|-------------------------|-----------------|
| AnyIO task groups | `asyncio.TaskGroup` (stdlib) | If zero-dependency async is mandatory | asyncio.TaskGroup lacks cancel scope control, task listing, and readiness signaling. AnyIO's API is a strict superset. |
| AnyIO task groups | Taskiq / ARQ | If you need distributed task queues with Redis broker | Over-engineered for local-first. Taskiq needs a broker (InMemoryBroker is dev-only). ARQ requires Redis. Our workload is "run N HTTP-polled jobs concurrently on one machine." |
| Pydantic BaseModel | stdlib frozen dataclasses | If absolute minimum dependencies is the constraint | Loses validation, JSON Schema, serialization. Existing dataclasses work but don't validate inputs or generate schemas for manifests. |
| Pydantic BaseModel | attrs | If you need extreme performance on model creation | Pydantic's Rust core is fast enough. attrs lacks built-in validation and JSON Schema generation. |
| SQLite (stdlib) | TinyDB | If you need zero-SQL document storage for <1K records | TinyDB has no ACID guarantees, degrades past 10K records, no concurrent access. Experiment tracking will exceed these limits. |
| SQLite (stdlib) | MLflow (full) | If team grows beyond solo researcher and needs UI + model registry | MLflow 3.9 is powerful but heavyweight (pulls in Flask, SQLAlchemy, many dependencies). Overkill for v1 local-first. Offer as optional `tracking` extra. |
| SQLite (stdlib) | MLflow Skinny | If you want MLflow's tracking API without the server | Still pulls in dependencies. For v1, raw SQLite gives more control over schema and query patterns specific to FK PINN scoring. |
| httpx | aiohttp | If you need WebSocket support | aiohttp API is less ergonomic than httpx. httpx matches requests API 1:1, making migration from existing `requests` client trivial. |
| httpx | requests + ThreadPoolExecutor | If async migration is blocked | Fragile. Thread pool polling is harder to cancel, harder to reason about, no structured concurrency. |
| PyYAML | OmegaConf + Hydra | If you need CLI config overrides and config composition | Hydra (1.3.2) is powerful but opinionated -- it wants to own your CLI, your config directory layout, and your app entry point. Conflicts with existing Typer CLI design. hydra-zen (0.16.0) reduces YAML but still requires Hydra runtime. |
| PyYAML | StrictYAML | If you want schema-validated YAML at parse time | StrictYAML (1.7.3) validates during parsing, but Pydantic already validates after parsing. Double validation adds complexity without benefit. |
| Typer | Click | If you need lower-level CLI control | Typer is built on Click. Drop down to Click when needed. No reason to start with Click directly. |
| Typer | argparse (existing) | Never | argparse requires boilerplate that Typer eliminates. Existing CLI is already the weakest layer. |
| structlog | loguru | If you want simpler logging setup with less configuration | Loguru is easier to set up but structlog's key-value structured output maps directly to experiment metadata (run_id, scenario params). For a research platform where logs ARE data, structured output matters. |
| Rich | plain print (existing) | Never for production | Current `_print_top()` uses bare `print()`. Unacceptable for a leaderboard with 50-200 results. Rich tables, progress bars, and color are table stakes for CLI research tools. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Celery | Heavyweight distributed task queue. Requires Redis/RabbitMQ broker. Synchronous by default -- async requires manual event loop management. Massive dependency tree. Completely wrong tool for local-first concurrent HTTP polling. | AnyIO task groups for structured async concurrency |
| Hydra (as primary config system) | Wants to own your entire application lifecycle: CLI, config directory, logging, working directory. Conflicts with Typer CLI, custom logging, and existing project structure. Last stable release 1.3.2 (Sep 2023) -- maintenance pace is slow. | PyYAML for manifest parsing + Pydantic for validation + Typer for CLI |
| Weights & Biases (wandb) | Cloud-first SaaS. Requires account + API key. Sends data to external servers. Violates local-first constraint. | SQLite for metadata + local filesystem for artifacts |
| Neptune.ai | Same as wandb -- cloud-first SaaS, not local-first. | SQLite + filesystem |
| DVC | Over-engineered for this use case. DVC is for versioning large datasets and creating ML pipelines with DAG execution. Our scenario manifests are small YAML files (version in git directly). Our artifacts are model checkpoints (store on filesystem, index in SQLite). | Git for config versioning + SQLite index + filesystem storage |
| Sacred | Abandoned/unmaintained. No Python 3.12+ support. MongoDB dependency for storage. | Pydantic + SQLite + custom tracking |
| TensorBoard | Visualization-only. No experiment management, no metadata queries, no reproducibility tracking. | SQLite for metadata (add visualization layer in v2 if needed) |
| MongoDB / PostgreSQL | Server-based databases. Violates local-first constraint. Operational overhead for solo researcher. | SQLite (stdlib) |
| Poetry | Slower than uv. uv is the emerging standard from Astral (same team as Ruff). | uv |

## Stack Patterns by Variant

**If extending to team use (v2):**
- Add `mlflow-skinny>=3.9.0` as optional dependency
- MLflow Tracking with SQLite backend (`sqlite:///mlruns.db`) for team-visible experiment dashboard
- Keep custom SQLite store for domain-specific FK PINN scoring queries that MLflow DSL cannot express
- MLflow Model Registry for model packaging if checkpoint lifecycle becomes complex

**If Python 3.10 must be preserved (constraint):**
- Drop `asyncio.TaskGroup` assumption (only available 3.11+)
- AnyIO still works on 3.10 (backports structured concurrency)
- This is the primary reason AnyIO is recommended over raw asyncio -- it provides the same API on 3.10

**If reproducibility metadata needs to be auditable:**
- Add `docker` Python SDK for capturing container environment hashes
- Add `pip-audit` for dependency vulnerability snapshots
- Add `uv pip freeze > requirements.lock` as part of run metadata

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pydantic>=2.12.5 | pydantic-settings>=2.13.0 | Same pydantic-core. Install together. |
| anyio>=4.12.1 | httpx>=0.28.0 | httpx uses anyio internally for async transport. Versions aligned. |
| typer>=0.21.0 | rich>=14.2.0 | Typer uses Rich for help formatting. `pip install "typer[all]"` pulls Rich. |
| typer>=0.21.0 | click>=8.1.0 | Typer is built on Click. Version pinned internally. |
| ruff>=0.15.1 | mypy>=1.19.1 | No interaction. Both are dev tools. |
| pytest>=9.0.2 | pytest-asyncio>=0.25.0 | Plugin compatibility confirmed. |
| hydra-core==1.3.2 | omegaconf>=2.2,<2.4 | Noted for reference only -- NOT recommended for this project. |

## Architecture Impact Summary

The stack choices above directly constrain the architecture:

1. **AnyIO + httpx** replaces the sequential `for scenario in scenarios: wait_until_terminal()` loop with concurrent task groups. Each scenario becomes an async task in a group, with structured cancellation on failure.

2. **Pydantic models** replace frozen dataclasses as the canonical data layer. Manifests (YAML) are parsed by PyYAML and validated by Pydantic. Results are Pydantic models serialized to SQLite.

3. **SQLite** becomes the single source of truth for experiment state. Replaces in-memory lists and CSV-only output. Enables: resume after crash, query by any dimension, historical comparison.

4. **Typer + Rich** replaces argparse + print(). The CLI becomes the primary research interface with progress bars, colored leaderboards, and structured output.

5. **structlog** provides queryable JSON logs tied to run IDs, replacing implicit print debugging.

## Migration Path from Existing Code

| Existing | Becomes | Effort |
|----------|---------|--------|
| `@dataclass(frozen=True) Scenario` | `class Scenario(BaseModel, frozen=True)` | Low -- field-for-field migration |
| `@dataclass(frozen=True) BatchConfig` | `class BatchConfig(BaseModel, frozen=True)` | Low -- same pattern |
| `requests.get/post` in `client.py` | `httpx.AsyncClient.get/post` | Medium -- async/await transformation |
| `for scenario in scenarios: wait()` in `orchestrator.py` | `async with anyio.create_task_group() as tg: tg.start_soon(run_scenario, s)` | Medium -- requires async refactor |
| `write_csv()` in `reporting.py` | SQLite INSERT + optional CSV export | Medium -- new persistence layer |
| `argparse` in `cli.py` | `typer.Typer()` app with commands | Low -- cleaner code, fewer lines |
| `print()` leaderboard | `rich.table.Table` + `rich.progress` | Low -- cosmetic improvement |

## Sources

- [Pydantic v2 docs (Context7: /pydantic/pydantic)](https://github.com/pydantic/pydantic) -- BaseModel, frozen config, dataclass interop | HIGH confidence
- [AnyIO docs (Context7: /agronholm/anyio)](https://github.com/agronholm/anyio) -- task groups, structured concurrency | HIGH confidence
- [MLflow docs (Context7: /websites/mlflow)](https://mlflow.org/docs/latest/) -- tracking, model registry, SQLite backend | HIGH confidence
- [Pydantic PyPI](https://pypi.org/project/pydantic/) -- v2.12.5 verified | HIGH confidence
- [pydantic-settings PyPI](https://pypi.org/project/pydantic-settings/) -- v2.13.0 verified | HIGH confidence
- [AnyIO PyPI](https://pypi.org/project/anyio/) -- v4.12.1 verified | HIGH confidence
- [MLflow PyPI](https://pypi.org/project/mlflow/) -- v3.9.0 stable verified | HIGH confidence
- [Typer PyPI](https://pypi.org/project/typer/) -- v0.21.0 verified | HIGH confidence
- [Rich PyPI](https://pypi.org/project/rich/) -- v14.2.0 verified | HIGH confidence
- [Ruff PyPI](https://pypi.org/project/ruff/) -- v0.15.1 verified | HIGH confidence
- [mypy PyPI](https://pypi.org/project/mypy/) -- v1.19.1 verified | HIGH confidence
- [pytest PyPI](https://pypi.org/project/pytest/) -- v9.0.2 verified | HIGH confidence
- [uv PyPI](https://pypi.org/project/uv/) -- v0.10.4 verified | HIGH confidence
- [PyYAML PyPI](https://pypi.org/project/PyYAML/) -- v6.0.3 verified | HIGH confidence
- [hydra-core PyPI](https://pypi.org/project/hydra-core/) -- v1.3.2 verified (not recommended) | HIGH confidence
- [hydra-zen PyPI](https://pypi.org/project/hydra-zen/) -- v0.16.0 verified (not recommended) | HIGH confidence
- [Best Tools for ML Experiment Tracking 2025 (Neptune.ai)](https://neptune.ai/blog/best-ml-experiment-tracking-tools) -- ecosystem survey | MEDIUM confidence
- [Who needs MLflow when you have SQLite? (Ploomber)](https://ploomber.io/blog/experiment-tracking/) -- SQLite vs MLflow for small teams | MEDIUM confidence
- [AnyIO vs asyncio.TaskGroup discussion](https://anyio.readthedocs.io/en/stable/why.html) -- why AnyIO over stdlib | MEDIUM confidence
- [Taskiq architecture (official docs)](https://taskiq-python.github.io/guide/architecture-overview.html) -- evaluated and rejected | MEDIUM confidence
- [MLflow with SQLite backend tutorial](https://mlflow.org/docs/latest/tracking/tutorials/local-database/) -- local tracking pattern | HIGH confidence
- [ML Reproducibility best practices (Neptune.ai)](https://neptune.ai/blog/how-to-solve-reproducibility-in-ml) -- seed, git SHA, environment tracking | MEDIUM confidence

---
*Stack research for: Feynman-Kac Quant Research Acceleration Platform*
*Researched: 2026-02-19*
