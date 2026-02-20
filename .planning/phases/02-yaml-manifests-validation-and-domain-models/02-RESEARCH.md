# Phase 2: YAML Manifests, Validation, and Domain Models - Research

**Researched:** 2026-02-20
**Domain:** YAML experiment configuration, Pydantic v2 schema validation, content-hash versioning, domain-specific parameter constraint validation, structured result schemas
**Confidence:** HIGH

## Summary

Phase 2 transforms the experiment definition workflow from CLI flags to version-controlled YAML manifest files with validated schemas and pre-flight domain validation. The current system (Phase 1 output) already has Pydantic v2 frozen models (`RunManifest`, `ScenarioResult`, `ManifestMetadata`, `ReproducibilityInfo`) and YAML serialization for output manifests. Phase 2 inverts this flow: instead of the orchestrator building a manifest from CLI args, the researcher writes an `experiment.yaml` defining the full experiment (scenario grid, batch config, scoring strategy, output paths), the platform validates it with Pydantic and domain-specific constraint validators, content-hashes it for versioning, and then executes it via `--manifest path/to/experiment.yaml`.

The phase has three distinct technical domains: (1) **YAML manifest schema design and loading** -- defining the researcher-facing YAML schema, loading it with `yaml.safe_load()` + `Model.model_validate()`, and content-hashing via `json.dumps(sort_keys=True)` + `hashlib.sha256()`; (2) **domain-specific pre-flight validation** -- checking that correlation matrices are positive semi-definite, volatilities are within sensible ranges, option types are compatible with scenario dimensions, and model/architecture sweep parameters are valid; (3) **structured result schema enforcement** -- tightening the existing `ScenarioResult` model with required fields (`status`, `train_loss`, `grad_norm`, `runtime_seconds`, `error_stats`, `rank_score`) and rejecting malformed results at write time.

All three domains use well-established patterns. The YAML-to-Pydantic validation pipeline is a standard ML experiment management pattern (used by Hydra, DVC, MLflow Projects). Content hashing with canonical JSON is the standard approach for config deduplication. Positive-definiteness checking via Cholesky decomposition is numerically stable and can be implemented in pure Python (avoiding a numpy dependency) for the small matrices involved (typically 2x2 to 20x20 correlation matrices in quant finance).

**Primary recommendation:** Design the experiment manifest as a hierarchy of Pydantic v2 frozen models loaded via `yaml.safe_load()` + `ExperimentManifest.model_validate()`. Use `@model_validator(mode='after')` for cross-field constraint validation (e.g., correlation matrix dimensions match `dim` list). Hash via `json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",",":")).encode("utf-8")` piped to `hashlib.sha256()`. Implement positive-definiteness check via pure-Python Cholesky to avoid adding numpy as a dependency. Add `--manifest` option to the existing Typer CLI as a new subcommand or option on `run-batch`.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| Pydantic | >=2.12.5 (installed) | Manifest schema definition, field/model validation, result schema enforcement | Already in use from Phase 1. `model_validate()` for YAML loading, `@field_validator` for range checks, `@model_validator(mode='after')` for cross-field constraints. `frozen=True` for immutability. `model_dump(mode="json")` for canonical serialization. | HIGH |
| PyYAML | >=6.0.3 (installed) | YAML loading/writing | Already in use from Phase 1. `yaml.safe_load()` for reading researcher manifests. `yaml.safe_dump(sort_keys=True)` for deterministic output. | HIGH |
| hashlib (stdlib) | Python stdlib | Content-hash computation | `hashlib.sha256()` on canonical JSON bytes. Zero-dependency, deterministic. | HIGH |
| json (stdlib) | Python stdlib | Canonical serialization for hashing | `json.dumps(data, sort_keys=True, separators=(",",":"))` produces a deterministic canonical form. No need for JCS or external canonicalization. | HIGH |
| math (stdlib) | Python stdlib | Pure-Python Cholesky decomposition for positive-definiteness checks | `math.sqrt()` for the inner loop. Avoids adding numpy as a dependency for small matrices (2x2 to 20x20). | HIGH |

### Supporting

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| Typer | >=0.21.0 (installed) | CLI `--manifest` option with Path validation | `typer.Option(..., exists=True, file_okay=True, dir_okay=False, readable=True)` for manifest file path validation. Already configured from Phase 1. | HIGH |
| structlog | >=25.5.0 (installed) | Structured validation error logging | Log pre-flight validation failures with context (which field, what value, what constraint). Already configured from Phase 1. | HIGH |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pure-Python Cholesky for PD check | numpy `np.linalg.cholesky()` or `np.linalg.eigvalsh()` | numpy adds a ~30MB dependency for a single check on small matrices. For 2x2 to 20x20 correlation matrices, pure-Python Cholesky is fast enough (<1ms) and correct. If the project later adds numpy for other reasons, can switch. |
| `json.dumps(sort_keys=True)` for canonical form | JCS (JSON Canonicalization Scheme, RFC 8785) via `python-jcs` | JCS handles edge cases (unicode normalization, number formatting) but adds a dependency. For our use case (Pydantic model_dump produces clean Python types), `json.dumps(sort_keys=True, separators=(",",":"))` is sufficient and deterministic. |
| Pydantic `@model_validator` for cross-field checks | Custom `validate()` classmethod | Pydantic validators are the standard Pydantic v2 pattern. They integrate with the validation pipeline, produce structured `ValidationError` objects, and work with `model_validate()`. Custom classmethods bypass the validation framework. |
| Single `ExperimentManifest` model | Separate models for each section (grid, config, scoring) composed manually | Composition is cleaner for large schemas, but for this use case the manifest is small enough (scenario grid + batch config + model sweep + scoring + output paths) that a single nested model hierarchy is simpler and validates cross-references (e.g., grid dimensions match correlation matrix size) in one pass. |
| `Literal` types for constrained enums | Raw string validation with `@field_validator` | `Literal["call", "put", "asian_call", "barrier_up_and_out"]` for option types is cleaner, provides auto-complete in IDEs, and generates correct JSON Schema. Validators are needed only for complex constraints. |

**Installation:**

No new dependencies required. All libraries are already installed from Phase 1.

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
src/fk_quant_research_accel/
    models/
        __init__.py          # Extended exports
        enums.py             # Extended with OptionType, ScoringStrategy enums
        ids.py               # Preserved from Phase 1
        manifest.py          # Extended: ExperimentManifest (researcher-facing YAML schema)
        result.py            # Tightened: required fields, strict validation
        hashing.py           # NEW: content_hash() for manifest versioning
    validation/              # NEW: domain-specific pre-flight validation
        __init__.py
        constraints.py       # is_positive_semidefinite(), validate_volatility_range(), etc.
        preflight.py         # validate_manifest() -- orchestrates all checks
    cli.py                   # Extended: --manifest option on run-batch
    orchestrator.py          # Modified: load manifest, validate, then execute
    ... (rest preserved from Phase 1)
```

### Pattern 1: YAML Manifest Schema as Pydantic Hierarchy

**What:** Define the researcher-facing YAML schema as a hierarchy of frozen Pydantic models. The top-level `ExperimentManifest` contains nested models for scenario grid, batch config, model sweep, scoring strategy, and output paths.

**When to use:** Parsing and validating any researcher-written experiment.yaml file.

**Example:**

```python
# Source: Pydantic v2 docs -- model_validate, frozen models, nested models
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self
import yaml

class ScenarioGridConfig(BaseModel, frozen=True):
    """Defines the PDE parameter sweep axes."""
    dimensions: list[int] = Field(..., min_length=1)
    volatilities: list[float] = Field(..., min_length=1)
    correlations: list[float] | list[list[float]] = Field(..., min_length=1)
    option_types: list[str] = Field(default_factory=lambda: ["call"])

    @field_validator("dimensions")
    @classmethod
    def dimensions_must_be_positive(cls, v: list[int]) -> list[int]:
        for d in v:
            if d < 1:
                raise ValueError(f"Dimension must be >= 1, got {d}")
        return v

    @field_validator("volatilities")
    @classmethod
    def volatilities_must_be_in_range(cls, v: list[float]) -> list[float]:
        for vol in v:
            if not (0.0 < vol <= 5.0):
                raise ValueError(
                    f"Volatility must be in (0.0, 5.0], got {vol}"
                )
        return v

class ModelSweepConfig(BaseModel, frozen=True):
    """Defines model/architecture sweep axes (CONF-07)."""
    architectures: list[str] = Field(default_factory=lambda: ["default"])
    hidden_sizes: list[list[int]] | None = None
    activations: list[str] | None = None
    optimizers: list[str] | None = None

class BatchRunConfig(BaseModel, frozen=True):
    """Training hyperparameters shared across all scenarios."""
    n_steps: int = Field(default=40, gt=0)
    batch_size: int = Field(default=64, gt=0)
    n_mc_paths: int = Field(default=256, gt=0)
    learning_rate: float = Field(default=1e-3, gt=0.0)
    poll_seconds: float = Field(default=1.5, gt=0.0)
    max_wait_seconds: float = Field(default=1800.0, gt=0.0)

class ScoringConfig(BaseModel, frozen=True):
    """Scoring strategy selection."""
    strategy: str = "loss_based"
    grad_norm_weight: float = Field(default=0.01, ge=0.0)

class OutputConfig(BaseModel, frozen=True):
    """Output path configuration."""
    artifacts_dir: str = "artifacts"
    db_path: str | None = None

class ExperimentManifest(BaseModel, frozen=True):
    """Top-level researcher-facing experiment manifest."""
    name: str | None = None
    description: str | None = None
    problem_id: str = "black_scholes"
    backend_url: str
    seed: int | None = None
    scenario_grid: ScenarioGridConfig
    model_sweep: ModelSweepConfig = Field(
        default_factory=ModelSweepConfig
    )
    batch_config: BatchRunConfig = Field(
        default_factory=BatchRunConfig
    )
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

def load_manifest(path: str) -> ExperimentManifest:
    """Load and validate an experiment manifest from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ExperimentManifest.model_validate(raw)
```

### Pattern 2: Content Hashing for Manifest Versioning (CONF-03)

**What:** Compute a deterministic SHA-256 hash of the manifest content so identical configs produce the same hash, and any parameter change produces a different hash. Hash the canonical JSON form, not the YAML text (YAML formatting variations should not affect the hash).

**When to use:** Every time a manifest is loaded, before execution begins.

**Example:**

```python
# Source: hashlib stdlib docs, Pydantic model_dump(mode="json")
import hashlib
import json

def content_hash(manifest: ExperimentManifest) -> str:
    """Compute deterministic SHA-256 hash of manifest content.

    Uses canonical JSON serialization: sorted keys, compact separators,
    no whitespace. Two identical manifests always produce the same hash.
    Any parameter change produces a different hash.
    """
    canonical = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**Why `model_dump(mode="json")` before `json.dumps()`:** Pydantic's `mode="json"` converts all types to JSON-native types (datetime to ISO string, Enum to value, etc.). This ensures the same data always produces the same JSON regardless of Python object identity. Combined with `sort_keys=True` and compact `separators`, the output is fully deterministic.

**Why NOT hash the YAML text:** YAML allows formatting variations (trailing newlines, comments, flow vs block style, key ordering). Two semantically identical YAML files can have different text. Hashing the YAML text would produce different hashes for equivalent configs.

### Pattern 3: Domain-Specific Pre-Flight Validation (CONF-05, CONF-06)

**What:** Validate that parameter combinations are physically meaningful before submitting any scenarios to the backend. Catch errors early with clear messages.

**When to use:** After manifest loading, before scenario generation or batch execution.

**Validation rules for Black-Scholes PINN experiments:**

1. **Positive semi-definite correlation matrices:** When `correlations` is a matrix (list of lists), verify all eigenvalues are non-negative. Use Cholesky decomposition (fails on non-PSD matrices).
2. **Volatility range check:** Volatilities must be in (0.0, 5.0] -- zero volatility is degenerate, >5.0 (500%) is almost certainly an error.
3. **Dimension-option compatibility:** Some option types require specific dimensions (e.g., basket options require dim >= 2, single-asset options require dim = 1 or are broadcast to multi-dim).
4. **Correlation matrix dimension match:** If correlations is a matrix, its size must equal max(dimensions) or each dimension in the sweep.
5. **Correlation value range:** Scalar correlations must be in [-1.0, 1.0]. Matrix diagonal must be 1.0.

**Example:**

```python
# Source: numpy.linalg.cholesky pattern adapted to pure Python, QuantStart
import math

def is_positive_semidefinite(matrix: list[list[float]], tol: float = 1e-10) -> bool:
    """Check if a symmetric matrix is positive semi-definite via Cholesky.

    Uses pure-Python Cholesky decomposition. For the small correlation
    matrices in quant finance (2x2 to 20x20), this is fast enough (<1ms)
    and avoids a numpy dependency.

    Returns True if the matrix is PSD, False otherwise.
    """
    n = len(matrix)
    if any(len(row) != n for row in matrix):
        return False  # Not square

    # Check symmetry
    for i in range(n):
        for j in range(i + 1, n):
            if abs(matrix[i][j] - matrix[j][i]) > tol:
                return False

    # Attempt Cholesky decomposition
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                val = matrix[i][i] - s
                if val < -tol:
                    return False  # Not PSD
                L[i][j] = math.sqrt(max(val, 0.0))
            else:
                if L[j][j] == 0.0:
                    return False
                L[i][j] = (matrix[i][j] - s) / L[j][j]
    return True


def validate_correlation_matrix(
    matrix: list[list[float]],
    expected_dim: int | None = None,
) -> list[str]:
    """Validate a correlation matrix. Returns list of error messages (empty = valid)."""
    errors: list[str] = []
    n = len(matrix)

    if expected_dim is not None and n != expected_dim:
        errors.append(
            f"Correlation matrix is {n}x{n} but dimension is {expected_dim}"
        )

    # Check diagonal is 1.0
    for i in range(n):
        if len(matrix[i]) != n:
            errors.append(f"Row {i} has {len(matrix[i])} elements, expected {n}")
            return errors  # Can't do further checks
        if abs(matrix[i][i] - 1.0) > 1e-10:
            errors.append(
                f"Diagonal element [{i}][{i}] is {matrix[i][i]}, must be 1.0"
            )

    # Check off-diagonal range [-1, 1]
    for i in range(n):
        for j in range(n):
            if i != j and not (-1.0 <= matrix[i][j] <= 1.0):
                errors.append(
                    f"Correlation [{i}][{j}] = {matrix[i][j]} is out of range [-1, 1]"
                )

    # Check positive semi-definite
    if not errors and not is_positive_semidefinite(matrix):
        errors.append("Correlation matrix is not positive semi-definite")

    return errors
```

### Pattern 4: Model/Architecture Sweep as First-Class Axis (CONF-07)

**What:** The manifest supports sweeping over model architectures (hidden layer sizes, activations, optimizers) alongside PDE parameter sweeps. The Cartesian product includes both axes.

**When to use:** When the researcher wants to compare different neural network configurations on the same PDE problem.

**YAML example:**

```yaml
# experiment.yaml -- sweeping both PDE params and model architecture
name: "vol-sweep-with-architecture-comparison"
problem_id: black_scholes
backend_url: http://localhost:8000

scenario_grid:
  dimensions: [5, 10]
  volatilities: [0.15, 0.2, 0.3]
  correlations: [0.0, 0.3]
  option_types: [call]

model_sweep:
  architectures: [fnn_3x64, fnn_4x128, resnet_3x64]
  # Optional: override per architecture
  hidden_sizes: [[64, 64, 64], [128, 128, 128, 128], [64, 64, 64]]
  activations: [tanh, relu, tanh]

batch_config:
  n_steps: 100
  batch_size: 128
  learning_rate: 0.001

scoring:
  strategy: loss_based
  grad_norm_weight: 0.01

output:
  artifacts_dir: artifacts
```

**Implementation:** The scenario grid Cartesian product is extended to include model sweep axes. Each generated scenario includes both PDE parameters and model configuration. The `Scenario` model (currently a frozen dataclass in `orchestrator.py`) must be extended to carry model config.

### Pattern 5: Structured Result Schema with Strict Validation (RSLT-01, RSLT-02)

**What:** Tighten the existing `ScenarioResult` model so that all results conform to a structured schema with required fields. Validate results before writing to SQLite or disk. Reject malformed results with clear error messages.

**When to use:** Every time a scenario result is collected from the backend, before persisting.

**Required fields per RSLT-01:** `status`, `train_loss`, `grad_norm`, `runtime_seconds`, `error_stats`, `rank_score`.

**Design decision:** The existing `ScenarioResult` allows most fields to be `None` (train_loss, grad_norm, etc.) because failed scenarios have no metrics. The requirement says "all run results conform to a structured schema with required fields" -- but failed runs legitimately lack metrics. Resolution: Define a `CompletedResult` model for successful scenarios (all metric fields required) and keep `FailedResult` for failed scenarios (error_message required, metrics optional). Use a discriminated union on `status`.

**Example:**

```python
# Source: Pydantic v2 docs -- discriminated unions, Literal
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Literal

class ErrorStats(BaseModel, frozen=True):
    """Error statistics from a completed scenario."""
    pde_residual: float | None = None
    boundary_error: float | None = None
    relative_l2_error: float | None = None

class CompletedScenarioResult(BaseModel, frozen=True):
    """Result schema for successfully completed scenarios."""
    status: Literal["completed"]
    scenario_run_id: str
    batch_run_id: str
    simulation_id: str
    scenario_params: dict[str, Any]
    train_loss: float
    grad_norm: float
    runtime_seconds: float
    error_stats: ErrorStats = Field(default_factory=ErrorStats)
    rank_score: float
    # Optional enrichment
    val_loss: float | None = None
    lr: float | None = None
    progress: float = 1.0
    checkpoint_path: str | None = None
    extra_metrics: dict[str, Any] = Field(default_factory=dict)

class FailedScenarioResult(BaseModel, frozen=True):
    """Result schema for failed scenarios."""
    status: Literal["failed"]
    scenario_run_id: str
    batch_run_id: str
    simulation_id: str | None = None
    scenario_params: dict[str, Any]
    error_message: str
    runtime_seconds: float = 0.0
    rank_score: float = float("inf")
    extra_metrics: dict[str, Any] = Field(default_factory=dict)

# Validation at write time:
def validate_and_build_result(raw: dict[str, Any]) -> CompletedScenarioResult | FailedScenarioResult:
    """Validate a raw result dict and return a typed result model.
    Raises ValidationError with clear messages on malformed data."""
    status = raw.get("status")
    if status == "completed":
        return CompletedScenarioResult.model_validate(raw)
    elif status == "failed":
        return FailedScenarioResult.model_validate(raw)
    else:
        raise ValueError(f"Unknown status '{status}'; expected 'completed' or 'failed'")
```

### Pattern 6: CLI `--manifest` Integration (CONF-02)

**What:** Add `--manifest` option to the Typer CLI so the researcher can run experiments from a YAML file instead of CLI flags.

**When to use:** Researcher has prepared an experiment.yaml and wants to execute it.

**Example:**

```python
# Source: Context7 /fastapi/typer -- Path parameter with exists validation
from pathlib import Path
import typer

@app.command("run-batch")
def run_batch_command(
    manifest: Path | None = typer.Option(
        None,
        "--manifest",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to experiment YAML manifest",
    ),
    base_url: str | None = typer.Option(None, "--base-url"),
    # ... other existing CLI options preserved for backward compat ...
) -> None:
    if manifest is not None:
        # Load and validate manifest
        experiment = load_manifest(str(manifest))
        manifest_hash = content_hash(experiment)
        log.info("manifest_loaded", path=str(manifest), hash=manifest_hash)

        # Run pre-flight validation
        errors = validate_manifest(experiment)
        if errors:
            for err in errors:
                log.error("preflight_validation_failed", error=err)
            raise typer.Exit(code=1)

        # Build scenarios from manifest
        scenarios = generate_scenarios_from_manifest(experiment)
        config = experiment.batch_config
        # ... proceed with run_batch
    else:
        # Existing CLI-flag-based path (backward compatible)
        ...
```

### Anti-Patterns to Avoid

- **Hashing YAML text instead of canonical JSON:** YAML formatting variations (whitespace, comments, key order) produce different hashes for semantically identical configs. Always hash the canonical JSON form.
- **Using `model_dump_json()` for hashing:** Pydantic's `model_dump_json()` output may not be deterministic across versions (key order is not guaranteed to be sorted). Use `json.dumps(model_dump(mode="json"), sort_keys=True)` explicitly.
- **Adding numpy just for PD check:** A 30MB dependency for a single linear algebra check on small matrices is disproportionate. Pure-Python Cholesky is sufficient for correlation matrices up to ~50x50.
- **Making ALL result fields required:** Failed scenarios legitimately lack metrics. Using a discriminated union (CompletedResult vs FailedResult) is cleaner than requiring sentinel values (e.g., train_loss=-1.0 for failed runs).
- **Validating inside the model only:** Cross-scenario validation (e.g., "does the correlation matrix dimension match the scenario dimension?") cannot be done in a single model validator because it requires iterating over the Cartesian product. Separate pre-flight validation function is needed.
- **Breaking backward compatibility with CLI flags:** The `--manifest` option should be additive. Existing `--base-url --dimensions ...` flags must continue to work for backward compatibility.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML schema validation | Custom dict traversal with key checks | Pydantic `model_validate()` on `yaml.safe_load()` output | Pydantic produces structured `ValidationError` with field paths, expected types, and received values. Manual dict checking misses nested validations and produces poor error messages. |
| Content hashing | Custom serialization + hashing | `json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",",":"))` + `hashlib.sha256()` | The canonical JSON approach is proven, deterministic, and handles all edge cases (None, datetime, nested dicts). Custom serialization will miss edge cases. |
| Positive-definiteness check | Hand-rolled eigenvalue computation | Pure-Python Cholesky decomposition | Cholesky is numerically stable for PSD checks and well-understood. Eigenvalue computation from scratch has more edge cases (convergence, complex arithmetic). |
| Range validation on fields | Custom `if` checks after model construction | Pydantic `Field(gt=0, le=5.0)` and `@field_validator` | Field constraints are declarative, generate JSON Schema, and produce standard validation errors. Manual checks after construction bypass the validation framework. |
| Discriminated union for result types | `if status == "completed": ...` branches everywhere | Pydantic discriminated union or explicit `model_validate()` dispatch on status | Centralizes the status-to-schema mapping. Pydantic validates all fields for the correct variant and produces specific errors for the wrong variant. |
| Scenario generation from manifest | Manual Cartesian product construction | `itertools.product()` over manifest grid axes (including model sweep axes) | `itertools.product()` handles arbitrary numbers of axes correctly. Manual nested loops become unwieldy when adding new sweep dimensions. |

**Key insight:** Phase 2 is primarily a Pydantic v2 validation problem. Every requirement maps to a Pydantic pattern: `model_validate()` for loading (CONF-01), `model_dump()` for hashing (CONF-03), `@field_validator`/`@model_validator` for constraints (CONF-05), `Field()` for range checks, frozen models for immutability, and discriminated unions for result schemas (RSLT-01/02).

## Common Pitfalls

### Pitfall 1: Non-Deterministic Hash from Floating-Point Serialization

**What goes wrong:** Two manifests with `volatility: 0.1` and `volatility: 0.10000000000000001` (IEEE 754 representation) produce different hashes because `json.dumps()` serializes them differently, even though they are the same float value.

**Why it happens:** Pydantic's `model_dump(mode="json")` preserves Python float values. Python's `json.dumps()` uses `repr()` for floats, which can vary across Python versions and platforms.

**How to avoid:** Use `json.dumps()` with Python 3.10+ where float serialization is consistent (CPython uses David Gay's dtoa algorithm). For extra safety, round floats to a fixed number of decimal places in the canonical form before hashing (e.g., 15 significant digits). Document that hash stability is guaranteed within the same Python minor version.

**Warning signs:** Same YAML file producing different hashes on different machines or Python versions.

### Pitfall 2: Correlation Scalar vs Matrix Ambiguity

**What goes wrong:** The researcher writes `correlations: [0.0, 0.3]` meaning "sweep over two scalar correlation values" but the validator interprets it as a 1x2 correlation matrix (which is non-square and invalid).

**Why it happens:** YAML represents both `list[float]` and `list[list[float]]` as nested sequences. The type `list[float] | list[list[float]]` is ambiguous when the inner list has one element.

**How to avoid:** Use explicit type discrimination in the YAML schema. When `correlations` is a list of scalars (e.g., `[0.0, 0.3, 0.5]`), it means "sweep over these scalar correlation values" (each applied uniformly). When `correlations` is a list of lists (e.g., `[[1.0, 0.3], [0.3, 1.0]]`), it means "use this single correlation matrix." Use a `@field_validator` that checks element types: if all elements are floats, treat as scalar sweep; if any element is a list, treat as matrix. Document this clearly in YAML schema docs.

**Warning signs:** Validation errors on valid scalar correlation lists, or silent acceptance of invalid matrix formats.

### Pitfall 3: Manifest Schema Evolution Breaking Old Manifests

**What goes wrong:** Adding a required field to `ExperimentManifest` in a future version means old YAML files fail validation. Researchers have committed manifests to git and expect them to keep working.

**Why it happens:** Pydantic required fields without defaults cause `ValidationError` when the field is missing from input.

**How to avoid:** Add a `manifest_version: int` field to the top level. New fields must always have defaults for the current version. Add a migration layer: if `manifest_version < CURRENT`, apply forward-migration transforms before validation. Never remove fields; deprecate with warnings. This mirrors the `PRAGMA user_version` pattern from Phase 1.

**Warning signs:** `ValidationError: field required` on old manifests after a schema update.

### Pitfall 4: Pre-Flight Validation Missing Cartesian Product Edge Cases

**What goes wrong:** The pre-flight validator checks each axis independently (all dimensions are positive, all volatilities are in range) but misses invalid *combinations* (e.g., dim=1 with a 5x5 correlation matrix, or `barrier_up_and_out` option with dim=20).

**Why it happens:** Field-level validators only see one field at a time. Model-level validators see all fields but don't enumerate the Cartesian product.

**How to avoid:** The pre-flight validation must enumerate the Cartesian product (or at least the constraint-relevant combinations) and check each scenario for validity. This is a separate pass after model validation -- not a Pydantic validator but a function that takes the validated manifest and returns a list of (scenario_params, error) tuples for invalid combinations. Log all invalid combinations at once, don't fail on the first one.

**Warning signs:** A manifest passes validation but scenarios fail at the backend with parameter errors.

### Pitfall 5: Overly Strict Result Schema Rejecting Backend Variations

**What goes wrong:** The backend returns `grad_norm: null` for a completed run (because the optimizer doesn't track gradient norms in some configurations). The strict result schema rejects it because `grad_norm: float` is required.

**Why it happens:** The requirement says "all run results conform to a structured schema with required fields" but the FK PINN backend's metric schema is not fully stable (see STATE.md blockers).

**How to avoid:** Define "required" as "must be present in the schema" but allow `None` for metrics that the backend may not provide. Use `float | None` with a default of `None` for metrics that are expected but not guaranteed. Log a warning when an expected metric is `None` for a completed run. The strict requirement applies to the result *structure* (all fields present) not the values (all fields non-null).

**Warning signs:** Completed scenarios being flagged as malformed because of null metrics.

### Pitfall 6: Model Sweep Generating Incompatible Backend Payloads

**What goes wrong:** The manifest specifies `architectures: [resnet_3x64]` but the FK PINN backend doesn't support a `resnet_3x64` architecture string. The model sweep generates scenarios that all fail at the backend.

**Why it happens:** The model sweep axis is passed through to the backend without validation against the backend's available architectures.

**How to avoid:** For Phase 2, model sweep values are opaque strings passed to the backend. Pre-flight validation should warn (not error) if architecture names don't match known patterns. Optionally, add a `--validate-backend` flag that queries `GET /api/v1/problems` to check which architectures are supported. Full backend validation is out of scope for Phase 2 (it requires network access during validation).

**Warning signs:** All scenarios in a model sweep batch fail with the same backend error.

## Code Examples

Verified patterns from official sources:

### Loading YAML and Validating with Pydantic v2

```python
# Source: Pydantic v2 docs (model_validate), PyYAML (safe_load)
# https://docs.pydantic.dev/2.12/concepts/models/#model-methods-and-properties
# https://www.sarahglasmacher.com/how-to-validate-config-yaml-pydantic/
import yaml
from pydantic import ValidationError

def load_and_validate_manifest(path: str) -> ExperimentManifest:
    """Load a YAML manifest file and validate against the schema.

    Raises:
        FileNotFoundError: If path does not exist.
        yaml.YAMLError: If YAML is malformed.
        ValidationError: If content fails schema validation.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError(f"Manifest file is empty: {path}")
    if not isinstance(raw, dict):
        raise ValueError(f"Manifest must be a YAML mapping, got {type(raw).__name__}")

    try:
        return ExperimentManifest.model_validate(raw)
    except ValidationError as exc:
        # Re-raise with file path context
        raise ValueError(
            f"Manifest validation failed for {path}:\n{exc}"
        ) from exc
```

### Deterministic Content Hash

```python
# Source: hashlib stdlib docs, Pydantic model_dump docs
# https://docs.python.org/3/library/hashlib.html
# https://docs.pydantic.dev/2.12/concepts/serialization/
import hashlib
import json

def content_hash(manifest: ExperimentManifest) -> str:
    """SHA-256 of the canonical JSON representation.

    Guarantees:
    - Identical manifests produce the same hash
    - Changing any parameter produces a different hash
    - Hash is stable across Python sessions (same Python version)
    """
    data = manifest.model_dump(mode="json")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

### Pure-Python Positive Semi-Definite Check

```python
# Source: Cholesky decomposition algorithm (Golub & Van Loan, Matrix Computations)
# Adapted from: https://www.quantstart.com/articles/Cholesky-Decomposition-in-Python-and-NumPy/
import math

def is_positive_semidefinite(matrix: list[list[float]], tol: float = 1e-10) -> bool:
    """Check PSD via Cholesky decomposition. Pure Python, no numpy."""
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                val = matrix[i][i] - s
                if val < -tol:
                    return False
                L[i][j] = math.sqrt(max(val, 0.0))
            else:
                if abs(L[j][j]) < tol:
                    return False
                L[i][j] = (matrix[i][j] - s) / L[j][j]
    return True
```

### Pydantic model_validator for Cross-Field Checks

```python
# Source: Pydantic v2 docs -- model_validator mode='after'
# https://docs.pydantic.dev/2.12/concepts/validators/
from pydantic import model_validator
from typing_extensions import Self

class ScenarioGridConfig(BaseModel, frozen=True):
    dimensions: list[int]
    volatilities: list[float]
    correlations: list[float] | list[list[float]]
    option_types: list[str] = ["call"]

    @model_validator(mode="after")
    def check_correlation_matrix_dimensions(self) -> Self:
        """If correlations is a matrix, validate its dimensions against scenario dims."""
        if not self.correlations:
            return self
        first = self.correlations[0]
        if isinstance(first, list):
            # It's a matrix
            matrix = self.correlations  # type: list[list[float]]
            n = len(matrix)
            for dim in self.dimensions:
                if dim > 1 and n != dim:
                    raise ValueError(
                        f"Correlation matrix is {n}x{n} but scenario dimension {dim} "
                        f"requires a {dim}x{dim} matrix"
                    )
        return self
```

### Typer Path Option with Validation

```python
# Source: Context7 /fastapi/typer -- Path parameter with exists validation
from pathlib import Path
import typer

@app.command("run-batch")
def run_batch_command(
    manifest: Path | None = typer.Option(
        None,
        "--manifest",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to experiment YAML manifest. Overrides all other config flags.",
    ),
    base_url: str | None = typer.Option(None, "--base-url"),
    # ... other flags for backward compatibility ...
) -> None:
    """Run a batch experiment from a manifest or CLI flags."""
    ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@validator` (Pydantic v1) | `@field_validator` / `@model_validator` (Pydantic v2) | Pydantic v2 (June 2023) | Explicit `mode` parameter, `@classmethod` decorator required, clearer semantics |
| `schema()` for JSON Schema | `model_json_schema()` (Pydantic v2) | Pydantic v2 (June 2023) | Generates JSON Schema Draft 2020-12 by default |
| `dict()` for serialization | `model_dump(mode="json")` (Pydantic v2) | Pydantic v2 (June 2023) | `mode="json"` converts all types to JSON-native for deterministic serialization |
| `parse_obj()` for validation | `model_validate()` (Pydantic v2) | Pydantic v2 (June 2023) | Renamed for clarity, same functionality |
| Manual YAML config loading | Pydantic `model_validate()` on `yaml.safe_load()` | Community pattern (2023+) | Standard ML experiment management pattern (Hydra, DVC, MLflow Projects all validate config schemas) |
| Hydra for config management | Pydantic + PyYAML (direct) | Project-specific choice | Hydra adds significant complexity (config composition, overrides, multirun). For a single researcher with explicit YAML files, Pydantic + PyYAML is simpler and sufficient. |

**Deprecated/outdated:**
- Pydantic v1 `@validator`: Replaced by `@field_validator` in v2. The old decorator still works but is deprecated.
- Pydantic v1 `@root_validator`: Replaced by `@model_validator` in v2.
- `yaml.load()` without Loader: Always use `yaml.safe_load()` (security -- arbitrary code execution risk).
- Sacred for experiment config: Abandoned, no Python 3.12+ support.

## Open Questions

1. **FK PINN Backend Architecture Strings**
   - What we know: The backend accepts a `problem_id` string and `training_config` dict. The current code hardcodes `problem_id="black_scholes"`.
   - What's unclear: Does the backend accept architecture specification in `training_config` (e.g., `{"architecture": "fnn_3x64"}`)? What architecture names are valid? Is there a list endpoint?
   - Recommendation: For Phase 2, treat architecture names as opaque strings passed to the backend in `training_config`. Pre-flight validation checks that architecture names are non-empty strings. Backend validation is deferred to Phase 3 or later.

2. **Result Schema Stability Across Backend Versions**
   - What we know: The backend metric schema has changed before (`metrics.get("loss", metrics.get("train_loss"))` in orchestrator.py). The blockers in STATE.md note "FK PINN backend metric schema needs auditing."
   - What's unclear: Which of the RSLT-01 required fields (`runtime_seconds`, `error_stats`) are actually returned by the backend? Does the backend return `error_stats` at all?
   - Recommendation: Define `runtime_seconds` as computed by the orchestrator (wall clock from submission to completion), not from the backend. Define `error_stats` with all-optional sub-fields (pde_residual, boundary_error, relative_l2_error). Populate from backend metrics if available, leave as None if not. The schema enforces structure, not completeness.

3. **Correlation Matrix Sweep Semantics**
   - What we know: The current codebase uses a single scalar `correlation` per scenario. CONF-05 requires matrix validation.
   - What's unclear: Should the manifest support sweeping over multiple correlation matrices? Or is it one matrix per experiment?
   - Recommendation: Support both: (a) `correlations: [0.0, 0.3, 0.5]` for scalar sweep (each value used uniformly), and (b) `correlations: [[1.0, 0.3], [0.3, 1.0]]` for a single explicit matrix. Sweeping over multiple matrices would require a list of matrices -- defer this to Phase 6 (extensibility) if needed.

4. **Backward Compatibility of `Scenario` Dataclass**
   - What we know: `Scenario` is currently a frozen dataclass with `dim`, `volatility`, `correlation`, `option_type`. Phase 2 adds model sweep fields.
   - What's unclear: Should `Scenario` be extended or should a new `EnrichedScenario` be created?
   - Recommendation: Migrate `Scenario` from a dataclass to a Pydantic frozen BaseModel. Add optional `model_config` field (dict) for architecture sweep parameters. This is a breaking change to the internal API but not to the YAML contract. Existing code that creates `Scenario(dim=5, ...)` will need minor updates.

## Sources

### Primary (HIGH confidence)

- [Pydantic v2 Validators Documentation](https://docs.pydantic.dev/2.12/concepts/validators/) -- `@field_validator`, `@model_validator`, mode parameter, Self return type (Context7 `/websites/pydantic_dev_2_12`)
- [Pydantic v2 Serialization Documentation](https://docs.pydantic.dev/2.12/concepts/serialization/) -- `model_dump(mode="json")`, deterministic serialization
- [Pydantic v2 Models Documentation](https://docs.pydantic.dev/latest/concepts/models/) -- `model_validate()`, frozen models, `model_json_schema()`
- [Python hashlib Documentation](https://docs.python.org/3/library/hashlib.html) -- SHA-256 content hashing
- [Typer Path Parameter Documentation](https://github.com/fastapi/typer/blob/master/docs/tutorial/parameter-types/path.md) -- Path validation with `exists`, `file_okay`, `readable` (Context7 `/fastapi/typer`)
- [NumPy linalg.cholesky Documentation](https://numpy.org/doc/stable/reference/generated/numpy.linalg.cholesky.html) -- Cholesky decomposition algorithm reference (Context7 `/numpy/numpy`)
- [NumPy linalg.eigvalsh Documentation](https://github.com/numpy/numpy/blob/main/doc/neps/reference/generated/numpy.linalg.eigvalsh.md) -- Eigenvalue computation for symmetric matrices (Context7)

### Secondary (MEDIUM confidence)

- [How to Validate Config YAML with Pydantic (Sarah Glasmacher)](https://www.sarahglasmacher.com/how-to-validate-config-yaml-pydantic/) -- YAML + Pydantic v2 integration pattern
- [Deterministic Hashing of Python Data Objects (death.andgravity.com)](https://death.andgravity.com/stable-hashing) -- Canonical JSON serialization for hashing, pitfalls with float repr
- [Pydantic Discussion #10343: Is model_dump_json deterministic?](https://github.com/pydantic/pydantic/discussions/10343) -- Confirms model_dump_json key order is not guaranteed sorted; use json.dumps with sort_keys
- [Pydantic Discussion #3323: Generate unique ID based on model content](https://github.com/pydantic/pydantic/discussions/3323) -- Community patterns for content-based model hashing
- [Cholesky Decomposition in Python (QuantStart)](https://www.quantstart.com/articles/Cholesky-Decomposition-in-Python-and-NumPy/) -- Pure-Python implementation, numerical considerations
- [Check Your Correlation Matrix (Janis Klaise)](https://www.janisklaise.com/post/check-your-correlation/) -- Correlation matrix validation pitfalls in finance
- [Finding the Nearest Valid Correlation Matrix (SITMO)](https://www.sitmo.com/finding-the-nearest-valid-correlation-matrix-with-highams-algorithm/) -- Higham's algorithm for fixing invalid correlation matrices
- [Black-Scholes Model Parameters (Macroption)](https://www.macroption.com/black-scholes-inputs/) -- Valid parameter ranges for Black-Scholes inputs
- [PINNs for Option Pricing (arXiv:2312.06711)](https://arxiv.org/html/2312.06711v1) -- PINN-specific parameter constraints for financial PDEs
- [PINNs for Option Pricing (MATLAB Blog, 2025)](https://blogs.mathworks.com/finance/2025/01/07/physics-informed-neural-networks-pinns-for-option-pricing/) -- PINN architecture considerations for Black-Scholes

### Tertiary (LOW confidence)

- [Validating YAML and TOML with Pydantic (C# Corner)](https://www.c-sharpcorner.com/article/validating-yaml-and-toml-configurations-in-python-with-pydantic/) -- Additional YAML validation patterns; not verified against Pydantic v2 specifically
- [pydantic-yaml PyPI package](https://pypi.org/project/pydantic-yaml/) -- Third-party Pydantic YAML integration; NOT recommended (direct yaml.safe_load + model_validate is simpler and avoids a dependency)

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH -- All libraries already installed from Phase 1. Pydantic v2 validation patterns verified via Context7 docs. Content hashing with json.dumps + hashlib.sha256 is stdlib and deterministic. PyYAML safe_load verified.
- Architecture: HIGH -- YAML-to-Pydantic validation pipeline is a proven ML experiment management pattern. Content hashing via canonical JSON is standard. Pre-flight validation as a separate pass (not just model validators) is necessary for cross-scenario constraints.
- Pitfalls: HIGH -- Float serialization non-determinism, correlation scalar/matrix ambiguity, schema evolution, and cross-field validation limitations are well-documented issues with verified mitigations.
- Domain validation: MEDIUM -- Black-Scholes parameter ranges are well-established in finance. Positive-definiteness via Cholesky is numerically standard. However, the exact option type / dimension compatibility rules depend on the FK PINN backend, which is not fully documented.

**Research date:** 2026-02-20
**Valid until:** 2026-03-20 (stable domain; 30-day validity)
