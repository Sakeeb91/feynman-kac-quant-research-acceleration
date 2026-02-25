# Phase 6: Extensibility - Research

**Researched:** 2026-02-25
**Domain:** Problem-type extensibility via ProblemSpec protocol, registry pattern, built-in migrations (BlackScholes, HarmonicOscillator)
**Confidence:** HIGH

## Summary

Phase 6 introduces a ProblemSpec protocol that decouples problem-type-specific logic (parameter schemas, scenario generation, validation, scoring defaults) from the orchestrator internals. The current codebase has Black-Scholes logic hardcoded in four locations: (1) the `Scenario` dataclass in `orchestrator.py` with fixed fields `dim`, `volatility`, `correlation`, `option_type`; (2) `generate_black_scholes_scenarios()` and `generate_scenarios_from_manifest()` that assume Black-Scholes parameter shapes; (3) hardcoded `problem_id="black_scholes"` strings in both `orchestrator.py:296` and `async_orchestrator.py:180`; and (4) Black-Scholes-specific validation in `validation/constraints.py` and `validation/preflight.py`. The `ExperimentManifest` already has a `problem_id: str = "black_scholes"` field (experiment.py:74), so the manifest schema is partially prepared.

The implementation will use Python's `typing.Protocol` with `@runtime_checkable` for the ProblemSpec contract, a dict-based registry for explicit registration, and Pydantic BaseModel subclasses for problem-specific parameter schemas. The scorer registry pattern from Phase 4 (`scoring/registry.py`) provides an excellent model -- the same decorator-based registration with dict lookup pattern can be adapted for ProblemSpec registration. The refactor-not-rewrite approach means wrapping existing Black-Scholes functions as a `BlackScholesSpec` class, then extracting the orchestrator's hardcoded paths into protocol dispatch calls.

**Primary recommendation:** Use `typing.Protocol` with `@runtime_checkable` for the ProblemSpec contract. Provide a concrete ABC-like base class `BaseProblemSpec` with default scorer/validator implementations that concrete specs can inherit from. Register specs in a module-level dict registry with a `register_problem` decorator, mirroring the existing `register_scorer` pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Protocol contract
- Strict core ProblemSpec contract with defaults for convenience
- Required members: `problem_id`, parameter schema (Pydantic model), scenario generator, validator, scorer entrypoint
- Flexible: scorer and validator can use default implementations so new specs can start minimal without breaking the contract
- A new ProblemSpec that only provides `problem_id`, parameter schema, and scenario generator should still be valid (defaults fill scorer/validator)

#### Scorer interaction
- Clear precedence chain to avoid Phase 4 / Phase 6 conflicts:
  - `custom_scorer` (manifest-level) > `ScoringConfig.strategy` (global) > ProblemSpec default scorer
- ProblemSpec can reject unsupported scoring strategies during validation (e.g., a problem type that doesn't support Pareto)
- ProblemSpec can provide problem-specific default Pareto objectives

#### Built-in migration
- Refactor existing code, don't rewrite from scratch
- First: wrap existing Black-Scholes logic as `BlackScholesSpec` -- generator, validator, scorer behavior unchanged
- Second: add `HarmonicOscillatorSpec` as a new implementation
- Then: remove hardcoded `"black_scholes"` submission paths; route through `problem_id` from selected spec
- Persist `problem_id` in run metadata so resume and analysis are unambiguous

#### Manifest experience
- Explicit registration (deterministic, testable) -- no auto-discovery / plugin scanning
- Manifest selects `problem_id` and has a problem-specific config section (e.g., `problem:` key)
- Errors for missing/invalid `problem_id` should list valid IDs and offer a nearest-match suggestion
- Backward compatibility: default to `black_scholes` when `problem_id` is omitted, but log a deprecation warning

### Claude's Discretion
- Exact ProblemSpec protocol shape (Protocol class vs ABC vs dataclass with methods)
- Registration mechanism internals (dict registry, decorator, or class-based)
- How default scorer/validator implementations are structured
- HarmonicOscillatorSpec parameter ranges and scenario generation details
- Deprecation warning format and log level

### Deferred Ideas (OUT OF SCOPE)
- Auto-discovery / plugin scanning for third-party ProblemSpecs -- keep it explicit for v1
- Problem-specific visualization or reporting hooks -- future enhancement
- Problem-specific CLI subcommands -- out of scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `typing.Protocol` | stdlib (3.14) | ProblemSpec structural interface | Standard Python approach for interface contracts; supports structural subtyping without inheritance requirement |
| `typing.runtime_checkable` | stdlib (3.14) | Runtime isinstance checks for Protocol | Enables validation that registered specs actually implement the contract |
| `pydantic` | >=2.12.5 | Problem-specific parameter schemas | Already used throughout codebase for all model validation |
| `difflib` | stdlib | Nearest-match suggestions on bad `problem_id` | `get_close_matches()` provides fuzzy matching for helpful error messages |
| `structlog` | >=25.5.0 | Deprecation warning logging | Already used throughout codebase for all logging |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `typing.get_protocol_members` | stdlib (3.14) | Protocol introspection | Available in Python 3.14 for debugging/validation of protocol members |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `typing.Protocol` | `abc.ABC` | ABC requires explicit inheritance; Protocol allows structural subtyping. Decision: Use Protocol for the interface definition, but provide a `BaseProblemSpec` convenience class that new specs CAN inherit from for default implementations |
| Dict registry | Decorator + entrypoints | Entrypoints add packaging complexity for no benefit when registration is explicit. Dict registry matches the existing `_SCORER_REGISTRY` pattern |
| Pydantic discriminated unions | Manual dispatch | Discriminated unions are elegant but require all parameter schemas to be known at import time. Manual dispatch via registry lookup is more extensible |

**No new dependencies required.** Everything uses stdlib `typing` + existing `pydantic`/`structlog`.

## Architecture Patterns

### Recommended Project Structure
```
src/fk_quant_research_accel/
├── problems/                    # NEW: Problem spec module
│   ├── __init__.py              # Public API: registry, get_problem_spec, register_problem
│   ├── protocol.py              # ProblemSpec Protocol + BaseProblemSpec base class
│   ├── registry.py              # Dict registry, register_problem decorator, get_problem_spec()
│   ├── black_scholes.py         # BlackScholesSpec (wraps existing orchestrator logic)
│   └── harmonic_oscillator.py   # HarmonicOscillatorSpec (new implementation)
├── models/
│   └── experiment.py            # Updated: problem_id field, problem: config key
├── orchestrator.py              # Updated: dispatch through ProblemSpec instead of hardcoded paths
├── async_orchestrator.py        # Updated: dispatch through ProblemSpec
├── validation/
│   └── preflight.py             # Updated: delegate to ProblemSpec.validate()
└── store/
    └── migrations.py            # Updated: schema v4 adds problem_id to batch_runs
```

### Pattern 1: Protocol + Base Class (Hybrid Approach)
**What:** Define a `typing.Protocol` for the contract, provide a `BaseProblemSpec` class with default implementations for convenience.
**When to use:** When you want structural typing for the interface but also want to provide sensible defaults that new implementations can inherit.
**Why chosen (Claude's Discretion):** This is the best fit for the user's locked decision: "strict core contract with defaults for convenience" and "new spec that only provides problem_id, parameter schema, and scenario generator should still be valid."

```python
# Source: Codebase pattern analysis + Python typing docs
from typing import Protocol, runtime_checkable, Any
from pydantic import BaseModel

class ProblemParams(BaseModel):
    """Base class for problem-specific parameter schemas."""
    pass

@runtime_checkable
class ProblemSpec(Protocol):
    """Core contract for problem type extensibility."""

    @property
    def problem_id(self) -> str: ...

    @property
    def param_schema(self) -> type[ProblemParams]: ...

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    def validate(
        self,
        params: dict[str, Any],
    ) -> list[str]: ...

    def default_scorer(
        self,
        record: dict[str, Any],
    ) -> float: ...

    def default_pareto_objectives(self) -> list[str]: ...

    def supports_scoring_strategy(self, strategy: str) -> bool: ...


class BaseProblemSpec:
    """Convenience base with default scorer/validator implementations.

    New problem types can inherit from this and only override what they need.
    Provides sensible defaults for validate(), default_scorer(),
    default_pareto_objectives(), and supports_scoring_strategy().
    """

    def validate(self, params: dict[str, Any]) -> list[str]:
        """Default: validate params against param_schema via Pydantic."""
        try:
            self.param_schema.model_validate(params)
            return []
        except Exception as exc:
            return [str(exc)]

    def default_scorer(self, record: dict[str, Any]) -> float:
        """Default: loss-based scoring (same as current loss_based strategy)."""
        train_loss = record.get("train_loss")
        if record.get("status") != "completed" or train_loss is None:
            return float("inf")
        return float(train_loss)

    def default_pareto_objectives(self) -> list[str]:
        return ["train_loss", "grad_norm"]

    def supports_scoring_strategy(self, strategy: str) -> bool:
        return True  # Default: support all strategies
```

### Pattern 2: Dict Registry with Decorator (Mirrors Scorer Registry)
**What:** Module-level dict mapping `problem_id` string to `ProblemSpec` instances, with a `register_problem` decorator for clean registration.
**When to use:** Explicit, deterministic registration -- the locked decision specifies no auto-discovery.

```python
# Source: Adapted from existing scoring/registry.py pattern
from __future__ import annotations
import difflib
from typing import Any

_PROBLEM_REGISTRY: dict[str, ProblemSpec] = {}

def register_problem(spec: ProblemSpec) -> ProblemSpec:
    """Register a ProblemSpec instance. Used at module level."""
    problem_id = spec.problem_id
    if problem_id in _PROBLEM_REGISTRY:
        raise ValueError(f"Duplicate problem_id registration: {problem_id!r}")
    _PROBLEM_REGISTRY[problem_id] = spec
    return spec

def get_problem_spec(problem_id: str) -> ProblemSpec:
    """Look up a registered ProblemSpec by ID."""
    # Ensure built-in specs are registered (lazy import, like scorer registry)
    import fk_quant_research_accel.problems.black_scholes as _bs
    import fk_quant_research_accel.problems.harmonic_oscillator as _ho
    _ = _bs, _ho

    try:
        return _PROBLEM_REGISTRY[problem_id]
    except KeyError:
        valid_ids = sorted(_PROBLEM_REGISTRY.keys())
        suggestions = difflib.get_close_matches(problem_id, valid_ids, n=1, cutoff=0.5)
        hint = f" Did you mean {suggestions[0]!r}?" if suggestions else ""
        raise ValueError(
            f"Unknown problem_id: {problem_id!r}. "
            f"Valid IDs: {valid_ids}.{hint}"
        ) from None

def list_problem_ids() -> list[str]:
    """Return all registered problem IDs (for error messages and docs)."""
    # Trigger lazy registration
    get_problem_spec.__wrapped__  # just access to trigger imports
    return sorted(_PROBLEM_REGISTRY.keys())
```

### Pattern 3: Scorer Precedence Chain
**What:** Resolve the effective scorer by checking: manifest `custom_scorer` > global `ScoringConfig.strategy` > ProblemSpec default scorer.
**When to use:** In the orchestrator, when determining which scorer function to apply to results.

```python
# Source: Locked decision on scorer interaction
from fk_quant_research_accel.scoring.registry import get_scorer, ScorerFn
from fk_quant_research_accel.models.experiment import ScoringConfig

def resolve_scorer(
    scoring_config: ScoringConfig,
    problem_spec: ProblemSpec,
) -> ScorerFn:
    """Resolve effective scorer using precedence chain."""
    # 1. Manifest custom_scorer always wins
    if scoring_config.custom_scorer:
        return get_scorer(scoring_config)

    # 2. Check if problem spec supports the configured strategy
    strategy = scoring_config.strategy
    if not problem_spec.supports_scoring_strategy(strategy.value):
        raise ValueError(
            f"Problem type {problem_spec.problem_id!r} does not support "
            f"scoring strategy {strategy.value!r}"
        )

    # 3. Global scoring strategy if explicitly configured (non-default)
    # The existing get_scorer handles this
    return get_scorer(scoring_config)
```

### Pattern 4: Backward-Compatible Manifest with Deprecation Warning
**What:** When `problem_id` is omitted from manifest, default to `"black_scholes"` and log a deprecation warning.
**When to use:** In manifest loading and the CLI run-batch command path.

```python
# Source: Locked decision on backward compatibility
import structlog

def resolve_problem_id_from_manifest(manifest: ExperimentManifest) -> str:
    """Resolve problem_id with backward compatibility."""
    log = structlog.get_logger()
    problem_id = manifest.problem_id

    # ExperimentManifest already defaults to "black_scholes"
    # If it came from default (field wasn't in YAML), log deprecation
    # Detection: check raw YAML for explicit problem_id presence
    # Alternative: just always log if it's "black_scholes"

    if problem_id == "black_scholes":
        # This will fire for both explicit and default -- acceptable
        # Users who explicitly set it won't mind the log line
        pass  # deprecation only if field was absent from YAML source

    return problem_id
```

### Pattern 5: DB Schema Migration (v3 -> v4)
**What:** Add `problem_id` column to `batch_runs` table for resume-batch and run analysis.
**When to use:** Required for persisting problem_id in run metadata.

```python
# Source: Existing migration pattern in store/migrations.py
def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    """Add problem_id column for extensibility (Phase 6)."""
    conn.execute(
        "ALTER TABLE batch_runs ADD COLUMN problem_id TEXT DEFAULT 'black_scholes'"
    )
```

### Anti-Patterns to Avoid
- **Putting problem logic in the orchestrator:** The whole point is to extract it OUT. Never add problem-specific if/elif chains in orchestrator.py.
- **Auto-discovery via `__init_subclass__` or importlib scanning:** Locked decision says explicit registration only.
- **Discriminated unions in the manifest for problem params:** This would require all parameter schemas to be statically known at manifest-validation time. Use a `dict[str, Any]` for the `problem:` config key with validation delegated to the spec.
- **Changing Scenario dataclass fields:** Instead of modifying the existing `Scenario` to be generic, make ProblemSpec.generate_scenarios() return `list[dict[str, Any]]` and let the orchestrator work with dicts. The Scenario class becomes internal to BlackScholesSpec.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy string matching for error messages | Levenshtein distance calculator | `difflib.get_close_matches()` | stdlib, well-tested, configurable cutoff |
| Protocol interface checking | Manual attribute checks | `isinstance(spec, ProblemSpec)` with `@runtime_checkable` | stdlib, type-checker compatible, Pythonic |
| Parameter validation | Custom validation logic per problem | Pydantic `model_validate()` on the param_schema | Reuses existing validation infrastructure, consistent error format |
| Registry pattern | Class metaclass magic | Dict + decorator (mirrors `_SCORER_REGISTRY`) | Simple, debuggable, tested pattern already in codebase |
| Default method dispatch | ABC with abstractmethod | `BaseProblemSpec` with concrete defaults | Allows structural subtyping via Protocol while providing inheritance convenience |

**Key insight:** The codebase already has a working registry pattern in `scoring/registry.py`. Reuse the same structure for ProblemSpec registration -- dict lookup, lazy import trigger, decorator for registration. Don't invent a new pattern.

## Common Pitfalls

### Pitfall 1: Circular Import from problems/ to scoring/
**What goes wrong:** `problems/black_scholes.py` imports from `scoring/registry.py` which imports from `models/experiment.py` which may import from `problems/` -- creating a circular dependency.
**Why it happens:** The scorer precedence chain creates a bidirectional dependency between problems and scoring.
**How to avoid:** Keep the `problems/` module independent of `scoring/`. The ProblemSpec protocol defines `default_scorer()` as a method returning float, not importing scorer functions. The precedence chain resolution lives in the orchestrator (or a new thin resolver module), not in the spec itself.
**Warning signs:** `ImportError` at module load time, or `AttributeError` on partially-initialized modules.

### Pitfall 2: Breaking Existing Tests During BlackScholes Migration
**What goes wrong:** Moving `Scenario`, `generate_black_scholes_scenarios`, `generate_scenarios_from_manifest` into `problems/black_scholes.py` breaks all 20+ imports in test files.
**Why it happens:** The refactor changes module paths for widely-used symbols.
**How to avoid:** Keep backward-compatible re-exports in `orchestrator.py`. After moving logic to `BlackScholesSpec`, add `from .problems.black_scholes import Scenario, generate_black_scholes_scenarios` in `orchestrator.py`. Deprecation warnings can be added later.
**Warning signs:** Mass test failures after first refactor step.

### Pitfall 3: Record Dict Shape Divergence Across Problem Types
**What goes wrong:** Black-Scholes records have `dim`, `volatility`, `correlation`, `option_type` as top-level keys. A harmonic oscillator would have `omega`, `mass`, `potential_type`. The orchestrator, diagnostics, comparison engine, and formatters all assume Black-Scholes field names.
**Why it happens:** The current system uses untyped `dict[str, Any]` for records, with field names hardcoded everywhere.
**How to avoid:** Establish a common record envelope: `simulation_id`, `status`, `progress`, `train_loss`, `val_loss`, `lr`, `grad_norm`, `score`, `convergence_health`, `error_message`, `checkpoint_path` are COMMON fields. Problem-specific parameters go into a nested `scenario_params: dict[str, Any]` key. The current `_build_failure_record()` and record-building code in both orchestrators already puts params at top level -- this needs to be refactored to use a `scenario_params` sub-dict.
**Warning signs:** `KeyError: 'dim'` when running harmonic oscillator scenarios through existing analysis code.

### Pitfall 4: Resume-Batch Doesn't Know Which ProblemSpec to Use
**What goes wrong:** `resume_batch_async()` currently reconstructs `Scenario` objects from stored `scenario_json`. After extensibility, it needs to know the problem_id to use the correct ProblemSpec for validation and submission.
**Why it happens:** `problem_id` is not persisted in the batch_runs table (current schema v3 doesn't have it).
**How to avoid:** The locked decision explicitly requires persisting `problem_id` in run metadata. Add it as a column in the schema v4 migration. Resume-batch reads it back and resolves the correct ProblemSpec.
**Warning signs:** Resume-batch silently assumes black_scholes for all problem types.

### Pitfall 5: Scenario Comparison Alignment Breaks for Different Problem Types
**What goes wrong:** `comparison.py:_scenario_key()` hardcodes `dim`, `volatility`, `correlation`, `option_type`, `model_config` as the alignment key. This won't work for harmonic oscillator scenarios.
**Why it happens:** The comparison engine assumes all scenarios share the same parameter shape.
**How to avoid:** Make `_scenario_key()` use a deterministic hash of the full `scenario_json` rather than extracting specific fields. Or have the ProblemSpec define which parameters constitute the scenario identity.
**Warning signs:** compare-runs shows zero matched scenarios when comparing two harmonic oscillator runs.

### Pitfall 6: Deprecation Warning Fires on Every Manifest Load
**What goes wrong:** Since `ExperimentManifest.problem_id` defaults to `"black_scholes"`, it's impossible to distinguish "user explicitly wrote problem_id: black_scholes" from "user omitted problem_id and got the default."
**Why it happens:** Pydantic defaults are applied during validation, erasing the distinction.
**How to avoid:** Use `model_fields_set` attribute -- Pydantic tracks which fields were explicitly provided. `if "problem_id" not in manifest.model_fields_set:` fires only when the field was actually omitted from the source data.
**Warning signs:** Researchers who explicitly specify `problem_id: black_scholes` get an unwanted deprecation warning.

## Code Examples

### BlackScholesSpec Wrapping Existing Logic

```python
# Source: Refactor of existing orchestrator.py:73-85 and orchestrator.py:124-151
from __future__ import annotations
import itertools
from typing import Any

from pydantic import BaseModel, Field, field_validator

from fk_quant_research_accel.problems.protocol import BaseProblemSpec, ProblemParams
from fk_quant_research_accel.problems.registry import register_problem
from fk_quant_research_accel.validation.constraints import (
    validate_correlation_matrix,
    validate_dimension_option_compatibility,
    validate_scalar_correlations,
    validate_volatility_range,
)


class BlackScholesParams(ProblemParams):
    """Parameter schema for Black-Scholes problem type."""
    dim: int = Field(gt=0)
    volatility: float = Field(gt=0.0, le=5.0)
    correlation: float | list[list[float]]
    option_type: str = "call"


class BlackScholesSpec(BaseProblemSpec):
    """Black-Scholes problem spec -- wraps existing generation/validation logic."""

    @property
    def problem_id(self) -> str:
        return "black_scholes"

    @property
    def param_schema(self) -> type[BlackScholesParams]:
        return BlackScholesParams

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Wraps existing generate_scenarios_from_manifest logic
        dimensions = grid_config["dimensions"]
        volatilities = grid_config["volatilities"]
        correlations = grid_config["correlations"]
        option_types = grid_config.get("option_types", ["call"])

        # Handle matrix correlations
        if correlations and isinstance(correlations[0], list):
            correlation_axis = (correlations,)
        else:
            correlation_axis = tuple(correlations)

        scenarios = []
        for dim, vol, corr, opt, mc in itertools.product(
            dimensions, volatilities, correlation_axis, option_types, model_configs,
        ):
            scenarios.append({
                "dim": dim,
                "volatility": vol,
                "correlation": corr,
                "option_type": getattr(opt, "value", opt),
                "model_config": dict(mc),
            })
        return scenarios

    def validate(self, params: dict[str, Any]) -> list[str]:
        # Wraps existing preflight validation from constraints.py
        errors: list[str] = []
        # Delegate to existing constraint validators
        # (full implementation wraps validate_volatility_range,
        #  validate_correlation_matrix, validate_dimension_option_compatibility, etc.)
        return errors


# Module-level registration
register_problem(BlackScholesSpec())
```

### HarmonicOscillatorSpec New Implementation

```python
# Source: Domain research + codebase pattern
from __future__ import annotations
import itertools
from typing import Any

from pydantic import BaseModel, Field

from fk_quant_research_accel.problems.protocol import BaseProblemSpec, ProblemParams
from fk_quant_research_accel.problems.registry import register_problem


class HarmonicOscillatorParams(ProblemParams):
    """Parameter schema for quantum harmonic oscillator problem type."""
    dim: int = Field(gt=0, le=10, description="Spatial dimensions")
    omega: float = Field(gt=0.0, le=100.0, description="Angular frequency")
    mass: float = Field(gt=0.0, default=1.0, description="Particle mass")
    potential_type: str = Field(
        default="quadratic",
        description="Potential type (quadratic, anharmonic)",
    )


class HarmonicOscillatorSpec(BaseProblemSpec):
    """Harmonic oscillator problem spec for Feynman-Kac PDE solver."""

    @property
    def problem_id(self) -> str:
        return "harmonic_oscillator"

    @property
    def param_schema(self) -> type[HarmonicOscillatorParams]:
        return HarmonicOscillatorParams

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        dimensions = grid_config.get("dimensions", [1])
        omegas = grid_config.get("omegas", [1.0])
        masses = grid_config.get("masses", [1.0])
        potential_types = grid_config.get("potential_types", ["quadratic"])

        scenarios = []
        for dim, omega, mass, potential_type, mc in itertools.product(
            dimensions, omegas, masses, potential_types, model_configs,
        ):
            scenarios.append({
                "dim": dim,
                "omega": omega,
                "mass": mass,
                "potential_type": potential_type,
                "model_config": dict(mc),
            })
        return scenarios

    def validate(self, params: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        omega = params.get("omega")
        if omega is not None and (omega <= 0.0 or omega > 100.0):
            errors.append(f"omega must be in (0.0, 100.0], got {omega}")
        mass = params.get("mass")
        if mass is not None and mass <= 0.0:
            errors.append(f"mass must be positive, got {mass}")
        return errors

    def default_pareto_objectives(self) -> list[str]:
        return ["train_loss", "grad_norm"]

    def supports_scoring_strategy(self, strategy: str) -> bool:
        return True  # Harmonic oscillator supports all scoring strategies


# Module-level registration
register_problem(HarmonicOscillatorSpec())
```

### Orchestrator Dispatch (Replacing Hardcoded Paths)

```python
# Source: Refactor of orchestrator.py:294-299 and async_orchestrator.py:178-184
# BEFORE (hardcoded):
simulation = client.create_simulation(
    problem_id="black_scholes",
    parameters=scenario.as_parameters(),
    training_config=batch_config.to_payload(),
)

# AFTER (dispatched via ProblemSpec):
simulation = client.create_simulation(
    problem_id=problem_spec.problem_id,
    parameters=scenario_params,
    training_config=batch_config.to_payload(),
)
```

### Manifest with Problem-Specific Config

```yaml
# Example manifest with harmonic oscillator
name: "harmonic-oscillator-sweep"
problem_id: harmonic_oscillator
backend_url: "http://localhost:8000"
scenario_grid:
  dimensions: [1, 2, 3]
  omegas: [0.5, 1.0, 2.0]
  masses: [1.0]
  potential_types: [quadratic]
model_sweep:
  architectures: [default]
batch_config:
  n_steps: 100
scoring:
  strategy: loss_based
```

### Deprecation Warning Using model_fields_set

```python
# Source: Pydantic v2 docs on model_fields_set
import structlog

def check_problem_id_deprecation(manifest: ExperimentManifest) -> None:
    """Log deprecation if problem_id was not explicitly set in manifest."""
    log = structlog.get_logger()
    if "problem_id" not in manifest.model_fields_set:
        log.warning(
            "problem_id_not_set",
            default="black_scholes",
            message=(
                "Manifest does not specify 'problem_id'. "
                "Defaulting to 'black_scholes'. "
                "This default will be removed in a future version. "
                "Please add 'problem_id: black_scholes' to your manifest."
            ),
        )
```

## Codebase Inventory: Files to Modify

This section catalogs every file that needs changes and what changes are needed, so the planner can create accurate task scopes.

### New Files
| File | Purpose |
|------|---------|
| `src/fk_quant_research_accel/problems/__init__.py` | Public API: `get_problem_spec`, `register_problem`, `list_problem_ids`, `ProblemSpec`, `BaseProblemSpec` |
| `src/fk_quant_research_accel/problems/protocol.py` | `ProblemSpec` Protocol + `BaseProblemSpec` base class + `ProblemParams` base |
| `src/fk_quant_research_accel/problems/registry.py` | Registry dict, `register_problem()`, `get_problem_spec()`, `list_problem_ids()` |
| `src/fk_quant_research_accel/problems/black_scholes.py` | `BlackScholesSpec`, `BlackScholesParams` -- wraps existing logic |
| `src/fk_quant_research_accel/problems/harmonic_oscillator.py` | `HarmonicOscillatorSpec`, `HarmonicOscillatorParams` |
| `tests/test_problems.py` | Tests for protocol, registry, BlackScholesSpec, HarmonicOscillatorSpec |

### Modified Files
| File | Change | Impact |
|------|--------|--------|
| `src/.../models/experiment.py` | Ensure `problem_id` field + add optional `problem: dict` config key | LOW -- field already exists |
| `src/.../orchestrator.py` | Replace hardcoded `problem_id="black_scholes"` with spec dispatch; keep backward-compatible re-exports | HIGH -- core refactor |
| `src/.../async_orchestrator.py` | Replace hardcoded `problem_id="black_scholes"` with spec dispatch | HIGH -- core refactor |
| `src/.../validation/preflight.py` | Delegate problem-specific validation to `ProblemSpec.validate()` | MEDIUM |
| `src/.../store/migrations.py` | Add v3->v4 migration with `problem_id` column on `batch_runs` | LOW |
| `src/.../store/metadata.py` | Accept and persist `problem_id` in `create_batch_run()` | LOW |
| `src/.../cli.py` | Pass `problem_id` through run-batch flow; handle deprecation warning | MEDIUM |
| `src/.../models/__init__.py` | Re-export problem types if needed | LOW |
| `src/.../__init__.py` | Update public API exports | LOW |
| `src/.../run_analysis/comparison.py` | Make `_scenario_key()` problem-agnostic | LOW |

### Hardcoded References to Remove
| Location | Current Code | Replacement |
|----------|-------------|-------------|
| `orchestrator.py:296` | `problem_id="black_scholes"` | `problem_id=problem_spec.problem_id` |
| `async_orchestrator.py:180` | `problem_id="black_scholes"` | `problem_id=problem_spec.problem_id` |
| `cli.py:190` | `generate_black_scholes_scenarios(...)` | `problem_spec.generate_scenarios(grid, model_configs)` |
| `cli.py:20` | `from .orchestrator import generate_black_scholes_scenarios` | `from .problems import get_problem_spec` |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `abc.ABC` + `@abstractmethod` | `typing.Protocol` + `@runtime_checkable` | Python 3.8+ (PEP 544) | Structural subtyping; no inheritance needed for conformance |
| Plugin entrypoints | Explicit registration | N/A (design decision) | Simpler, deterministic, testable |
| Pydantic v1 discriminated unions | Pydantic v2 `model_fields_set` | Pydantic 2.0 | Can detect which fields were explicitly set vs defaulted |

**Deprecated/outdated:**
- `abc.ABCMeta` for interface definition: Still works but `typing.Protocol` is preferred for structural subtyping (PEP 544, standard since Python 3.8)
- Plugin entrypoints (`entry_points` in setup.py/pyproject.toml): Overkill for this use case where all specs ship with the package

## HarmonicOscillator Domain Notes (Claude's Discretion)

The quantum harmonic oscillator Feynman-Kac PDE problem has these typical parameter ranges for a PINN solver:

| Parameter | Typical Range | Default | Description |
|-----------|---------------|---------|-------------|
| `dim` | 1-10 | 1 | Spatial dimensions |
| `omega` | 0.1-100.0 | 1.0 | Angular frequency |
| `mass` | 0.1-10.0 | 1.0 | Particle mass (often normalized to 1) |
| `potential_type` | quadratic, anharmonic | quadratic | Potential function shape |

The scenario grid for harmonic oscillator uses different sweep axes than Black-Scholes:
- Instead of `volatilities` and `correlations`, it uses `omegas` and `masses`
- Instead of `option_types`, it uses `potential_types`
- `dimensions` is shared with Black-Scholes

This reinforces the need for the `problem:` config key in the manifest rather than hardcoding grid axes in `ScenarioGridConfig`.

**Confidence:** MEDIUM -- parameter ranges are based on literature review and typical PINN solver configurations. The exact ranges should be validated against the FK PINN backend's actual capabilities.

## Open Questions

1. **ScenarioGridConfig vs problem-specific grid config**
   - What we know: The current `ScenarioGridConfig` is Black-Scholes-specific (dimensions, volatilities, correlations, option_types). Harmonic oscillator needs different axes (omegas, masses, potential_types).
   - What's unclear: Should we keep `ScenarioGridConfig` for backward compatibility and add a generic `problem:` dict for problem-specific config? Or should we make the scenario grid itself a problem-specific schema?
   - Recommendation: Keep `scenario_grid` for backward compatibility with existing Black-Scholes manifests. Add an optional `problem:` key at the manifest top level for problem-specific extensions. BlackScholesSpec reads from `scenario_grid`; HarmonicOscillatorSpec reads from `problem:` (or its own section of `scenario_grid` if the grid is made extensible). The simplest approach: ProblemSpec.generate_scenarios() receives the full manifest dict and extracts what it needs.

2. **Record field normalization across problem types**
   - What we know: Current records have Black-Scholes-specific fields (`dim`, `volatility`, `correlation`, `option_type`) at the top level. The comparison engine and formatters assume these fields exist.
   - What's unclear: How deeply to refactor the record format in Phase 6 vs deferring to a later phase.
   - Recommendation: Introduce a `scenario_params` sub-dict in records for problem-specific fields. Common fields (score, train_loss, etc.) stay at top level. This is a required change for multi-problem-type correctness but should be backward-compatible if existing code checks for top-level keys with `.get()`.

3. **Manifest schema for HarmonicOscillator grid**
   - What we know: The manifest needs problem-specific grid parameters.
   - What's unclear: Whether to use `scenario_grid` with problem-specific keys or a separate top-level key.
   - Recommendation: Use a `problem:` top-level key in the manifest for problem-specific configuration. BlackScholesSpec uses `scenario_grid` (backward compat). HarmonicOscillatorSpec reads its grid from `problem:` key. This keeps existing manifests working while supporting new problem types cleanly.

## Sources

### Primary (HIGH confidence)
- Python `typing.Protocol` documentation: https://docs.python.org/3/library/typing.html
- PEP 544 (Protocols: Structural subtyping): https://peps.python.org/pep-0544/
- Pydantic v2 discriminated unions: https://docs.pydantic.dev/latest/concepts/unions
- Pydantic v2 `model_fields_set`: https://docs.pydantic.dev/latest/ (verified via Context7)
- Codebase: `scoring/registry.py` -- existing registry pattern (HIGH, direct source inspection)
- Codebase: `orchestrator.py`, `async_orchestrator.py` -- hardcoded `problem_id` locations (HIGH, direct source inspection)
- Codebase: `models/experiment.py:74` -- existing `problem_id` field (HIGH, direct source inspection)
- Python `difflib.get_close_matches`: stdlib, verified locally

### Secondary (MEDIUM confidence)
- Harmonic oscillator PINN parameters: https://arxiv.org/html/2401.02810v1
- PINN quantum harmonic oscillator: https://github.com/AnishD11/PINN-Quantum-Harmonic-Oscillator
- Quantum harmonic oscillator: https://en.wikipedia.org/wiki/Quantum_harmonic_oscillator
- Real Python -- Python Protocols: https://realpython.com/python-protocol/
- Mypy protocols documentation: https://mypy.readthedocs.io/en/stable/protocols.html

### Tertiary (LOW confidence)
- HarmonicOscillatorSpec parameter ranges: Based on literature survey, not validated against FK PINN backend

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib + existing codebase dependencies, no new packages
- Architecture: HIGH -- Protocol pattern well-understood, registry mirrors existing scorer pattern, all source files inspected
- Pitfalls: HIGH -- identified 6 specific pitfalls from direct codebase analysis, each with concrete file locations
- HarmonicOscillator domain: MEDIUM -- parameter ranges from literature, not backend-validated
- Record normalization: MEDIUM -- correct approach identified, scope of refactor TBD

**Research date:** 2026-02-25
**Valid until:** 2026-03-25 (stable domain, no fast-moving dependencies)
