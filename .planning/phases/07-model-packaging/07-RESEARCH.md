# Phase 7: Model Packaging - Research

**Researched:** 2026-02-25
**Domain:** Self-contained model package export with checkpoint/weights, reproducibility metadata, validation summary, and manifest for the winning run of any batch
**Confidence:** HIGH

## Summary

Phase 7 adds an `export-model` CLI command that takes the winning scenario run from a completed batch and assembles a self-contained directory package containing everything needed to reproduce that specific training run and use the resulting model downstream. The package includes: the checkpoint/weights file (already persisted in `artifacts/{batch_run_id}/{scenario_run_id}/checkpoint/model_checkpoint.pt` by Phase 1's `_fetch_checkpoint`), the exact training config (from `batch_runs.config_json`), the scenario config (from `scenario_runs.scenario_json`), the seed (from `batch_runs.seed`), full environment metadata (git SHA, Python version, OS info, package versions -- all captured by `capture_environment()` and `capture_git_info()` in `models/manifest.py`), a validation summary (final metrics, convergence health from `result.json`, acceptance threshold results), and a package manifest describing all contents.

The existing codebase already captures and persists nearly all of the required data. The `RunManifest` model (in `models/manifest.py`) contains `ReproducibilityInfo` with git SHA, Python version, OS info, packages, and seed. The `MetadataStore` SQLite database has `batch_runs` (with `config_json`, `git_sha`, `python_version`, `os_info`, `seed`, `artifact_path`, `problem_id`) and `scenario_runs` (with `scenario_json`, `result_json`, `score`, `checkpoint_path`, `status`). The `ArtifactStore` already writes per-scenario `result.json` files containing `train_loss`, `val_loss`, `grad_norm`, `score`, `convergence_health`, `checkpoint_path`, and other metrics. The key implementation work is: (1) identifying the winning run from the DB, (2) copying/assembling these artifacts into a new self-contained package directory, (3) generating a validation summary with acceptance thresholds, (4) writing a package manifest, and (5) wiring it through the CLI.

**Primary recommendation:** Build a `ModelPackager` class in a new `src/fk_quant_research_accel/packaging/` module that reads from `MetadataStore` + `ArtifactStore`, assembles the package directory, and is invoked by a new `export-model` Typer CLI command. Use existing Pydantic models for the package manifest schema and YAML serialization (matching the existing `RunManifest` pattern). No new dependencies required.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pydantic` | >=2.12.5 | Package manifest schema, validation summary schema | Already used for all model validation in the codebase |
| `PyYAML` | >=6.0.3 | Serialize package manifest to YAML | Already used for RunManifest serialization in `models/manifest.py` |
| `typer` | >=0.21.0 | `export-model` CLI command | Already used for all CLI commands |
| `rich` | >=14.2.0 | CLI feedback during export (progress, summary table) | Already used for leaderboard and run analysis output |
| `structlog` | >=25.5.0 | Structured logging during export | Already used throughout codebase |
| `hashlib` | stdlib | SHA-256 integrity checksums for package contents | Already used for manifest content hashing in `models/hashing.py` |
| `shutil` | stdlib | Copy checkpoint files into package directory | Stdlib, standard for file copy operations |
| `json` | stdlib | Read/write result.json, scenario_json, config_json | Already used throughout codebase |
| `pathlib` | stdlib | Path manipulation for package assembly | Already used throughout codebase |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `zipfile` | stdlib | Optional zip compression of the package directory | If `--zip` flag is provided on CLI |
| `datetime` | stdlib | Timestamp the package creation | Already used for all time operations in the codebase |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| YAML manifest | JSON manifest | YAML matches existing `RunManifest` serialization pattern and is more human-readable; JSON is simpler but less consistent with existing codebase |
| Directory-based package | tar.gz or zip archive | Directory is easier to inspect, modify, and use downstream; archive can be optionally supported via `--zip` flag |
| Copy checkpoint into package | Symlink to original artifact dir | Symlinks break if artifacts are moved or cleaned up; copy ensures self-containment (per PKG-04) |
| Pydantic schema for manifest | Raw dict + json.dumps | Pydantic gives validation, serialization, and type safety; consistent with existing pattern |

**No new dependencies required.** Everything uses stdlib + existing dependencies.

## Architecture Patterns

### Recommended Project Structure
```
src/fk_quant_research_accel/
├── packaging/                    # NEW: Model packaging module
│   ├── __init__.py               # Public API: export_model_package, ModelPackageManifest
│   ├── manifest.py               # ModelPackageManifest, ValidationSummary Pydantic schemas
│   ├── assembler.py              # ModelPackager class: reads DB + artifacts, writes package
│   └── acceptance.py             # Acceptance threshold checks (convergence health, loss bounds)
├── cli.py                        # Updated: add export-model command
├── models/manifest.py            # Existing: ReproducibilityInfo reused for package
├── store/metadata.py             # Existing: query winning run data
└── store/artifacts.py            # Existing: atomic writes for package files
```

### Pattern 1: Winning Run Identification
**What:** Query the MetadataStore to find the best-scoring completed scenario within a batch.
**When to use:** First step of `export-model` -- determining which scenario run to package.
**Why this approach:** The orchestrator already sorts results by score (`sorted(records, key=lambda row: row["score"])`), and the DB persists per-scenario scores. The winning run is the completed scenario with the minimum `score` value (lower is better).

```python
# Source: Codebase analysis of orchestrator.py:465, store/metadata.py:164
def find_winning_scenario(store: MetadataStore, batch_run_id: str) -> dict[str, Any]:
    """Find the best-scoring completed scenario in a batch."""
    scenarios = store.get_scenario_runs(batch_run_id)
    completed = [
        s for s in scenarios
        if s.get("status") == "completed" and s.get("score") is not None
    ]
    if not completed:
        raise ValueError(
            f"No completed scenarios with scores in batch '{batch_run_id}'"
        )
    # Lower score is better (consistent with orchestrator sort)
    winner = min(completed, key=lambda s: float(s["score"]))
    return winner
```

### Pattern 2: Package Directory Layout
**What:** Standard directory structure for the self-contained model package.
**When to use:** During package assembly.
**Why this approach:** Mirrors ML model packaging conventions (MLflow, HuggingFace model cards). Easy to inspect, version-control, and consume downstream.

```
model_package_{batch_run_id_prefix}_{scenario_run_id_prefix}/
├── MANIFEST.yaml              # Package manifest (all contents described)
├── checkpoint/
│   └── model_checkpoint.pt    # Weights/checkpoint file copied from artifacts
├── config/
│   ├── training_config.yaml   # BatchConfig (n_steps, batch_size, lr, etc.)
│   ├── scenario_config.yaml   # Scenario parameters (dim, volatility, etc.)
│   └── experiment_manifest.yaml  # Full original manifest if available
├── environment/
│   ├── reproducibility.yaml   # Git SHA, Python version, OS, packages
│   └── seed.txt               # Random seed (if set)
├── validation/
│   ├── metrics.yaml           # Final train_loss, val_loss, grad_norm, score
│   ├── convergence_health.yaml  # Health label + diagnostic details
│   └── acceptance.yaml        # Acceptance threshold results (pass/fail)
└── README.txt                 # Human-readable summary of the package
```

### Pattern 3: Package Manifest Schema (Pydantic)
**What:** Strongly-typed manifest describing all package contents, using Pydantic for validation and YAML serialization.
**When to use:** Written as the final step of package assembly.
**Why this approach:** Mirrors `RunManifest` pattern in `models/manifest.py`. Provides machine-readable inventory of the package.

```python
# Source: Pattern from models/manifest.py:RunManifest
from pydantic import BaseModel, Field
from datetime import datetime

class PackageMetrics(BaseModel, frozen=True):
    train_loss: float | None = None
    val_loss: float | None = None
    grad_norm: float | None = None
    score: float | None = None
    convergence_health: str | None = None
    progress: float | None = None

class AcceptanceResult(BaseModel, frozen=True):
    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)

class ModelPackageManifest(BaseModel, frozen=True):
    package_version: int = 1
    created_at: datetime
    batch_run_id: str
    scenario_run_id: str
    problem_id: str
    checkpoint_file: str | None = None
    checkpoint_sha256: str | None = None
    training_config: dict[str, Any]
    scenario_config: dict[str, Any]
    seed: int | None = None
    reproducibility: ReproducibilityInfo  # Reuse from models/manifest.py
    metrics: PackageMetrics
    acceptance: AcceptanceResult
    contents: list[str]  # Relative paths of all files in the package
```

### Pattern 4: Acceptance Thresholds
**What:** Configurable checks that validate the winning run meets quality criteria before packaging.
**When to use:** During validation summary generation. Checks are informational (package is still created), but the summary clearly shows pass/fail status.
**Why this approach:** Prevents accidentally exporting a diverged or unhealthy run. The researcher sees at a glance whether the model meets their standards.

```python
# Source: Design pattern from diagnostics/health.py convergence checks
from fk_quant_research_accel.models.enums import ConvergenceHealth

DEFAULT_ACCEPTANCE_CHECKS = [
    {"name": "convergence_healthy", "check": "convergence_health in (healthy,)"},
    {"name": "loss_finite", "check": "train_loss is finite"},
    {"name": "score_finite", "check": "score is finite"},
]

def check_acceptance(
    metrics: dict[str, Any],
    convergence_health: str,
) -> tuple[bool, list[dict[str, Any]]]:
    """Run acceptance threshold checks on the winning scenario."""
    results = []
    all_passed = True

    # Check 1: Convergence health
    is_healthy = convergence_health == ConvergenceHealth.HEALTHY.value
    results.append({
        "name": "convergence_healthy",
        "passed": is_healthy,
        "actual": convergence_health,
        "expected": "healthy",
    })
    if not is_healthy:
        all_passed = False

    # Check 2: Loss is finite
    train_loss = metrics.get("train_loss")
    loss_ok = train_loss is not None and math.isfinite(float(train_loss))
    results.append({
        "name": "loss_finite",
        "passed": loss_ok,
        "actual": train_loss,
    })
    if not loss_ok:
        all_passed = False

    # Check 3: Score is finite
    score = metrics.get("score")
    score_ok = score is not None and math.isfinite(float(score))
    results.append({
        "name": "score_finite",
        "passed": score_ok,
        "actual": score,
    })
    if not score_ok:
        all_passed = False

    return all_passed, results
```

### Pattern 5: CLI Command Shape
**What:** A Typer command that accepts a run selector (same `resolve_run_id` pattern from Phase 5) and an output directory, then produces the package.
**When to use:** Invoked by the researcher after a batch completes.

```python
# Source: Pattern from cli.py show-run command + run_analysis/resolver.py
@app.command("export-model")
def export_model_command(
    run_id: str = typer.Argument(
        ...,
        help="Batch run to export from (UUID, prefix, latest, latest~N)",
    ),
    output_dir: str = typer.Option(
        "model_packages",
        "--output-dir",
        help="Directory to create the package in",
    ),
    scenario_id: str | None = typer.Option(
        None,
        "--scenario-id",
        help="Export specific scenario (default: best-scoring)",
    ),
    db_path: str = typer.Option(
        "artifacts/experiments.db",
        "--db-path",
    ),
    artifacts_dir: str = typer.Option(
        "artifacts",
        "--artifacts-dir",
    ),
    zip_package: bool = typer.Option(
        False,
        "--zip",
        help="Compress the package into a .zip file",
    ),
) -> None:
    ...
```

### Anti-Patterns to Avoid
- **Modifying existing artifact directories:** The package must be a NEW directory, never mutate the existing `artifacts/{batch_run_id}/{scenario_run_id}/` structure. Other tools (resume, analysis) depend on that structure being stable.
- **Embedding absolute paths in the manifest:** All paths in the package manifest must be RELATIVE to the package root. Absolute paths break when the package is moved.
- **Hard-coupling to Black-Scholes field names:** The scenario config should be stored as the raw `scenario_json` dict from the DB, not assuming specific field names (dim, volatility, etc.). Phase 6 made problem types extensible.
- **Requiring the FK PINN backend to be running:** The export must work entirely from local data (DB + artifact files). It should never make HTTP calls to the backend during export.
- **Silently skipping missing checkpoints:** If the checkpoint file is missing, the packager should warn loudly and still produce the package (metadata is still valuable for reproducibility), but the manifest must clearly indicate the checkpoint is absent.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Run selector resolution | Custom UUID/prefix parsing | Existing `resolve_run_id()` from `run_analysis/resolver.py` | Already handles `latest`, `latest~N`, UUID prefix matching -- tested in Phase 5 |
| Reproducibility info capture | Custom environment snapshot | Existing `capture_environment()` + `capture_git_info()` from `models/manifest.py` | Already captures Python version, OS, packages, git SHA/dirty -- tested in Phase 1 |
| Convergence health diagnosis | Custom metric analysis | Existing `diagnose_convergence()` from `diagnostics/health.py` | Already classifies healthy/oscillating/stagnating/exploding -- tested in Phase 4 |
| YAML serialization | Custom serializer | `yaml.safe_dump()` matching `write_manifest()` pattern | Already used for RunManifest serialization, handles datetime, nested dicts |
| Atomic file writes | Manual temp-file + rename | Existing `ArtifactStore.atomic_write_json()`, `atomic_write_text()`, `atomic_write_bytes()` | Already handles atomic writes with .tmp intermediates -- tested in Phase 1 |
| Content hashing | Custom hash function | `hashlib.sha256` matching `content_hash()` pattern from `models/hashing.py` | Consistent with existing codebase hashing approach |
| Score comparison (lower-is-better) | Custom comparator | `min(completed, key=lambda s: float(s["score"]))` | Consistent with orchestrator's `sorted(records, key=lambda row: row["score"])` |

**Key insight:** Phase 7 is primarily an assembly/packaging phase. Nearly all the raw data it needs is already captured and persisted by Phases 1-6. The main work is querying that data, copying/transforming it into a self-contained directory, and adding the validation summary + manifest.

## Common Pitfalls

### Pitfall 1: Checkpoint File Missing or Moved
**What goes wrong:** The `checkpoint_path` in the DB points to `artifacts/{batch}/{scenario}/checkpoint/model_checkpoint.pt`, but the file has been deleted, moved, or was never fetched (the FK backend may not always provide checkpoints).
**Why it happens:** The `_fetch_checkpoint` function in both orchestrators returns `None` when checkpoints are unavailable (`checkpoint_not_available` log), and the record stores `checkpoint_path: None`. Even when fetched, a user could have cleaned up the artifacts directory.
**How to avoid:** Always check `Path(checkpoint_path).exists()` before copying. If missing, log a warning, set `checkpoint_file: null` in the package manifest, and add a failing acceptance check (`checkpoint_present: false`). The package should still be created -- the reproducibility metadata alone is valuable.
**Warning signs:** `FileNotFoundError` during package assembly; or a package that claims to contain a checkpoint but doesn't.

### Pitfall 2: Batch Has No Completed Scenarios
**What goes wrong:** All scenarios in the batch failed, so there's no "winning run" to export.
**Why it happens:** Backend errors, timeout, invalid parameters -- all result in `status='failed'` with `score=inf`.
**How to avoid:** Check for completed scenarios before attempting export. Raise a clear `ValueError` with a helpful message: "Batch {id} has N scenarios, all failed. Nothing to export." This should be caught in the CLI layer and converted to `typer.Exit(code=1)`.
**Warning signs:** `min()` on an empty sequence raises `ValueError`; or exporting a package with `score: inf` and no useful metrics.

### Pitfall 3: result_json Is Stored as a JSON String in SQLite
**What goes wrong:** Directly writing `scenario_row["result_json"]` to a YAML file produces a YAML string containing JSON, not a proper YAML structure.
**Why it happens:** `persist_scenario_result()` stores `json.dumps(record)` as a text column. When read back, it's a string that must be `json.loads()`-ed before YAML serialization.
**How to avoid:** Always `json.loads()` the `result_json` and `scenario_json` columns before writing to YAML. The `_parse_json_object()` helper in `run_analysis/formatters.py` is a good pattern to follow (handles None and invalid JSON gracefully).
**Warning signs:** YAML files contain escaped JSON strings instead of structured data.

### Pitfall 4: Package Directory Name Collision
**What goes wrong:** Two exports of the same batch overwrite each other in the output directory.
**Why it happens:** Using only `batch_run_id` in the directory name, or not checking for existing directories.
**How to avoid:** Include both batch_run_id prefix and scenario_run_id prefix in the package name (e.g., `model_pkg_{batch[:8]}_{scenario[:8]}`). Check if the output directory already exists; if so, raise an error or add a `--force` flag to overwrite.
**Warning signs:** Silent data loss when exporting multiple times.

### Pitfall 5: Environment Metadata at Package Time vs Run Time
**What goes wrong:** Capturing `capture_environment()` during export gives the CURRENT environment (maybe Python 3.15 on a different machine), not the environment the training run actually used.
**Why it happens:** Confusion between "record the current state" and "copy the recorded state."
**How to avoid:** Read the environment metadata from the stored `RunManifest` YAML file (`artifacts/{batch}/manifest.yaml`) or from the `batch_runs` DB row (`python_version`, `os_info`, `git_sha`, `git_dirty`). Do NOT call `capture_environment()` or `capture_git_info()` during export. Only capture CURRENT environment for a separate `exported_from` metadata section (optional).
**Warning signs:** Package claims it was trained on Python 3.15 when the training actually ran on Python 3.14.

### Pitfall 6: DB Connection Left Open After Export
**What goes wrong:** The `MetadataStore` connection isn't closed if an error occurs during export.
**Why it happens:** Missing try/finally pattern around MetadataStore usage.
**How to avoid:** Use the same try/finally pattern established in `cli.py` for all DB-accessing commands (e.g., `list-runs`, `show-run`). Open store, do work in try block, close in finally.
**Warning signs:** SQLite lock contention if another process tries to access the DB during export.

### Pitfall 7: Non-Deterministic YAML Output
**What goes wrong:** Same package contents produce different YAML files (different key ordering, different datetime formatting), making it impossible to verify package integrity.
**Why it happens:** Python dicts have stable insertion order in 3.7+, but `yaml.safe_dump()` may reorder keys.
**How to avoid:** Use `sort_keys=True` in `yaml.safe_dump()` (matching the existing `write_manifest()` pattern). For Pydantic models, use `model.model_dump(mode="json")` before YAML serialization to ensure consistent datetime formatting.
**Warning signs:** Diffing two exports of the same run shows whitespace or ordering differences.

## Code Examples

### Reading the Winning Run from the Database

```python
# Source: Codebase analysis of store/metadata.py + run_analysis/resolver.py
import json
from typing import Any

from fk_quant_research_accel.store.metadata import MetadataStore
from fk_quant_research_accel.run_analysis.resolver import resolve_run_id


def get_winning_scenario(
    store: MetadataStore,
    batch_run_id: str,
    scenario_run_id: str | None = None,
) -> dict[str, Any]:
    """Get the winning (or specified) scenario from a batch."""
    scenarios = store.get_scenario_runs(batch_run_id)

    if scenario_run_id is not None:
        # User specified a specific scenario
        matches = [s for s in scenarios if s["scenario_run_id"] == scenario_run_id]
        if not matches:
            raise ValueError(
                f"Scenario '{scenario_run_id}' not found in batch '{batch_run_id}'"
            )
        return matches[0]

    # Find best-scoring completed scenario
    completed = [
        s for s in scenarios
        if s.get("status") == "completed" and s.get("score") is not None
    ]
    if not completed:
        raise ValueError(
            f"No completed scenarios with scores in batch '{batch_run_id}'. "
            f"Total scenarios: {len(scenarios)}, "
            f"statuses: {[s.get('status') for s in scenarios]}"
        )
    return min(completed, key=lambda s: float(s["score"]))
```

### Reading RunManifest from Existing Artifact Directory

```python
# Source: Existing artifact structure in artifacts/{batch_run_id}/manifest.yaml
import yaml
from pathlib import Path


def read_run_manifest(
    artifacts_dir: str | Path,
    batch_run_id: str,
) -> dict[str, Any]:
    """Read the RunManifest YAML written during batch execution."""
    manifest_path = Path(artifacts_dir) / batch_run_id / "manifest.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Run manifest not found at {manifest_path}. "
            f"Was the batch run created with this artifacts directory?"
        )
    with manifest_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

### Assembling the Package Directory

```python
# Source: Codebase patterns from store/artifacts.py + models/manifest.py
import shutil
import hashlib
from pathlib import Path

def assemble_package(
    output_dir: Path,
    checkpoint_source: Path | None,
    training_config: dict,
    scenario_config: dict,
    reproducibility: dict,
    metrics: dict,
    acceptance_results: list[dict],
    seed: int | None,
) -> Path:
    """Create the self-contained package directory structure."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # checkpoint/
    checkpoint_sha256 = None
    if checkpoint_source is not None and checkpoint_source.exists():
        ckpt_dir = output_dir / "checkpoint"
        ckpt_dir.mkdir(exist_ok=True)
        dest = ckpt_dir / checkpoint_source.name
        shutil.copy2(checkpoint_source, dest)
        checkpoint_sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()

    # config/
    config_dir = output_dir / "config"
    config_dir.mkdir(exist_ok=True)
    _write_yaml(config_dir / "training_config.yaml", training_config)
    _write_yaml(config_dir / "scenario_config.yaml", scenario_config)

    # environment/
    env_dir = output_dir / "environment"
    env_dir.mkdir(exist_ok=True)
    _write_yaml(env_dir / "reproducibility.yaml", reproducibility)
    if seed is not None:
        (env_dir / "seed.txt").write_text(str(seed), encoding="utf-8")

    # validation/
    val_dir = output_dir / "validation"
    val_dir.mkdir(exist_ok=True)
    _write_yaml(val_dir / "metrics.yaml", metrics)
    _write_yaml(val_dir / "acceptance.yaml", {
        "passed": all(r["passed"] for r in acceptance_results),
        "checks": acceptance_results,
    })

    return output_dir
```

### CLI export-model Command

```python
# Source: Pattern from cli.py show-run command
@app.command("export-model")
def export_model_command(
    run_id: str = typer.Argument(
        ..., help="Batch run to export (UUID, prefix, latest, latest~N)"
    ),
    output_dir: str = typer.Option("model_packages", "--output-dir"),
    scenario_id: str | None = typer.Option(None, "--scenario-id"),
    db_path: str = typer.Option("artifacts/experiments.db", "--db-path"),
    artifacts_dir: str = typer.Option("artifacts", "--artifacts-dir"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing package"),
    zip_package: bool = typer.Option(False, "--zip", help="Compress to .zip"),
) -> None:
    log = structlog.get_logger()
    store = MetadataStore(db_path)
    try:
        resolved = resolve_run_id(run_id, store)
        batch_run = store.get_batch_run(resolved)
        if batch_run is None:
            raise ValueError(f"No run found for selector: {run_id}")
        # ... assembly logic ...
    except ValueError as exc:
        log.error("export_model_failed", run_id=run_id, error=str(exc))
        raise typer.Exit(code=1) from exc
    finally:
        store.close()
```

## Data Flow Analysis

### What Data Is Already Available (from Phases 1-6)

| Data Needed (PKG-02..05) | Source | Location | Format |
|---------------------------|--------|----------|--------|
| Checkpoint/weights | `_fetch_checkpoint()` (Phase 1) | `artifacts/{batch}/{scenario}/checkpoint/model_checkpoint.pt` | Binary `.pt` file |
| Training config | `batch_config.to_payload()` | `batch_runs.config_json` in SQLite | JSON string: `{"n_steps", "batch_size", "n_mc_paths", "learning_rate"}` |
| Scenario config | `scenario.as_parameters()` | `scenario_runs.scenario_json` in SQLite | JSON string with problem-specific params |
| Seed | `ExperimentManifest.seed` | `batch_runs.seed` in SQLite | Integer or NULL |
| Git SHA | `capture_git_info()` | `batch_runs.git_sha` in SQLite, also in `manifest.yaml` | 40-char hex string |
| Git dirty flag | `capture_git_info()` | `batch_runs.git_dirty` in SQLite | Integer 0/1 |
| Python version | `capture_environment()` | `batch_runs.python_version` in SQLite, also in `manifest.yaml` | String e.g. "3.14.3" |
| OS info | `capture_environment()` | `batch_runs.os_info` in SQLite | String e.g. "macOS-15.6.1-arm64-..." |
| Package versions | `capture_environment()` | `manifest.yaml` in artifact dir | Dict of {name: version} |
| Final metrics | Orchestrator result record | `scenario_runs.result_json` in SQLite, also `result.json` file | JSON with train_loss, val_loss, grad_norm, score, etc. |
| Convergence health | `diagnose_convergence()` | Inside `result_json` as `convergence_health` field | String: "healthy"/"oscillating"/"stagnating"/"exploding" |
| Score | Scorer function | `scenario_runs.score` in SQLite | Float (lower is better) |
| Problem ID | Phase 6 extensibility | `batch_runs.problem_id` in SQLite | String e.g. "black_scholes" |
| Manifest hash | `content_hash()` | `batch_runs.manifest_hash` in SQLite | SHA-256 hex string |

### What Needs to Be Built (New for Phase 7)

| Component | Purpose | Complexity |
|-----------|---------|------------|
| `find_winning_scenario()` | Query DB for best-scoring completed scenario | LOW -- simple min() on score |
| `ModelPackageManifest` schema | Pydantic model for package manifest YAML | LOW -- follows RunManifest pattern |
| `PackageMetrics` schema | Pydantic model for validation metrics | LOW -- subset of existing result fields |
| `AcceptanceResult` schema | Pydantic model for acceptance checks | LOW -- simple pass/fail structure |
| `check_acceptance()` | Run acceptance checks on metrics + health | LOW -- 3-5 simple boolean checks |
| `assemble_package()` | Copy files, write configs, create directory | MEDIUM -- file I/O orchestration |
| `write_package_manifest()` | Generate and write MANIFEST.yaml | LOW -- follows write_manifest() pattern |
| `generate_readme()` | Human-readable summary text | LOW -- template string |
| `export-model` CLI command | Typer command with options | MEDIUM -- follows existing CLI patterns |
| Optional zip support | Compress package to .zip | LOW -- stdlib zipfile |

## Codebase Inventory: Files to Modify

### New Files
| File | Purpose |
|------|---------|
| `src/fk_quant_research_accel/packaging/__init__.py` | Public API: `export_model_package`, `ModelPackageManifest` |
| `src/fk_quant_research_accel/packaging/manifest.py` | `ModelPackageManifest`, `PackageMetrics`, `AcceptanceResult` Pydantic schemas |
| `src/fk_quant_research_accel/packaging/assembler.py` | `ModelPackager` class -- reads DB + artifacts, writes package directory |
| `src/fk_quant_research_accel/packaging/acceptance.py` | `check_acceptance()` function + default threshold definitions |
| `tests/test_packaging.py` | Tests for all packaging functionality |

### Modified Files
| File | Change | Impact |
|------|--------|--------|
| `src/.../cli.py` | Add `export-model` command importing from `packaging` | LOW -- additive, no existing behavior changed |
| `src/.../__init__.py` | Optionally re-export packaging public API | LOW -- additive |

### Files NOT Modified (read-only dependencies)
| File | How Used |
|------|----------|
| `store/metadata.py` | `get_batch_run()`, `get_scenario_runs()` -- read winning run data |
| `store/artifacts.py` | `atomic_write_json()`, `atomic_write_text()` -- write package files |
| `run_analysis/resolver.py` | `resolve_run_id()` -- resolve run selector from CLI arg |
| `models/manifest.py` | `ReproducibilityInfo` -- reused in package manifest |
| `diagnostics/health.py` | `diagnose_convergence()` -- could re-diagnose for validation summary |

**Key observation:** This phase is purely additive. It reads from existing storage layers and produces new output. No existing behavior needs to change.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual artifact copying | Structured model packaging | Standard in MLflow/W&B since ~2020 | Self-contained, portable model artifacts |
| No integrity checks | SHA-256 checksums per file | Common practice | Detect corruption during transfer |
| Implicit reproducibility | Explicit environment manifest | MLflow Model Registry pattern | Can recreate training environment from scratch |

**Deprecated/outdated:**
- Pickling entire model + environment: Insecure and non-portable. Use explicit metadata + standardized checkpoint format instead.
- Relying on Docker images for reproducibility: Heavyweight. Package-level metadata (packages dict, Python version) is sufficient for research reproducibility.

## Open Questions

1. **FK PINN Backend Checkpoint Format and Size**
   - What we know: The orchestrator fetches checkpoints via `checkpoint_url` (HTTP download) or `checkpoint_inline` (base64 encoded). They're stored as `model_checkpoint.pt` (PyTorch convention). The test uses `b"checkpoint-bytes"` as a mock.
   - What's unclear: Actual file sizes (KB? MB? GB?), whether the format is standard PyTorch `state_dict` or something custom, and whether the backend always provides checkpoints for completed simulations.
   - Impact on Phase 7: If checkpoints can be very large (>100MB), the `--zip` option becomes more important. If checkpoints are sometimes unavailable, the "missing checkpoint" handling in Pitfall 1 is critical.
   - Recommendation: Handle both cases (present and absent). Log a clear warning when absent. Don't block package creation on checkpoint availability.

2. **Acceptance Threshold Configurability**
   - What we know: PKG-03 requires "acceptance threshold results" in the validation summary. The simplest implementation is a set of hardcoded checks (convergence healthy, loss finite, score finite).
   - What's unclear: Should acceptance thresholds be configurable via the experiment manifest or CLI flags? (e.g., `--max-loss 0.01`).
   - Recommendation: Start with hardcoded sensible defaults. Accept an optional `--max-loss` CLI flag for the most common case. Full configurability can be deferred.

3. **Package Version Schema Migration**
   - What we know: The manifest has a `package_version: 1` field for forward compatibility.
   - What's unclear: What would trigger a v2 package format?
   - Recommendation: Include the version field from day 1. Document what it means. Don't over-engineer migration logic yet.

4. **Original Experiment Manifest Availability**
   - What we know: The `ExperimentManifest` YAML file is read at run time from the `--manifest` path. It's NOT stored in the artifact directory. The `RunManifest` in `artifacts/{batch}/manifest.yaml` captures `experiment_manifest_hash` and `batch_config` but NOT the full original manifest.
   - What's unclear: Is the original manifest YAML needed in the package? It would be the most complete reproducibility record.
   - Recommendation: Since we have `manifest_hash` in the DB, we can't reconstruct the original file. Include what we have: `batch_config`, `scenario_config`, `seed`, `problem_id`. Note in the README that the original manifest hash is recorded for verification. Optionally accept `--manifest-path` on the CLI to include the original file.

5. **Whether `--scenario-id` Should Accept Prefix Matching**
   - What we know: `resolve_run_id()` supports prefix matching and `latest` syntax for batch run IDs.
   - What's unclear: Should the `--scenario-id` option support similar prefix matching?
   - Recommendation: Start with exact match only. Scenario IDs within a batch are typically few (5-200), and the researcher can use `show-run` to find the exact ID. Prefix matching for scenario IDs adds complexity without proportional value.

## Sources

### Primary (HIGH confidence)
- Codebase: `store/metadata.py` -- MetadataStore API, batch_runs and scenario_runs schema (direct source inspection)
- Codebase: `store/migrations.py` -- SQLite schema v1-v4, all column definitions (direct source inspection)
- Codebase: `store/artifacts.py` -- ArtifactStore API, atomic write methods (direct source inspection)
- Codebase: `models/manifest.py` -- RunManifest, ReproducibilityInfo, capture_environment(), capture_git_info() (direct source inspection)
- Codebase: `models/result.py` -- CompletedScenarioResult, ErrorStats schema (direct source inspection)
- Codebase: `orchestrator.py` -- _fetch_checkpoint(), run_batch(), record building (direct source inspection)
- Codebase: `async_orchestrator.py` -- _fetch_checkpoint() async version, record building (direct source inspection)
- Codebase: `cli.py` -- Typer command patterns, resolve_run_id usage (direct source inspection)
- Codebase: `diagnostics/health.py` -- diagnose_convergence(), ConvergenceHealth enum (direct source inspection)
- Codebase: `run_analysis/resolver.py` -- resolve_run_id() signature and behavior (direct source inspection)
- Codebase: `models/hashing.py` -- content_hash() pattern for SHA-256 checksumming (direct source inspection)
- Codebase: `artifacts/966b90fe.../manifest.yaml` -- actual artifact structure on disk (direct inspection)
- Codebase: `tests/test_orchestrator.py:308-322` -- checkpoint persistence test showing expected file layout (direct inspection)

### Secondary (MEDIUM confidence)
- MLflow Model Packaging: standard practice for model_dir + MLmodel manifest + conda.yaml -- informs directory layout pattern
- PyTorch model saving conventions: `state_dict` + metadata pattern -- informs checkpoint file naming

### Tertiary (LOW confidence)
- Actual FK PINN backend checkpoint format: Unknown from codebase alone; test mock uses `b"checkpoint-bytes"`. Real format, size, and availability are backend-dependent.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all stdlib + existing packages
- Architecture: HIGH -- all source files inspected, all data sources verified to exist in DB schema and artifact layout, patterns directly derived from existing codebase
- Pitfalls: HIGH -- 7 pitfalls identified from concrete codebase analysis (DB column types, file existence checks, connection management)
- Data flow: HIGH -- every data field traced from its origin (capture function) through storage (DB column or file) to packaging output
- Acceptance thresholds: MEDIUM -- sensible defaults designed, but configurability scope is a design choice not yet locked
- Checkpoint format: LOW -- actual backend checkpoint format/size unknown; implementation handles both present and absent cases

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable domain, no fast-moving dependencies; all data comes from existing codebase)
