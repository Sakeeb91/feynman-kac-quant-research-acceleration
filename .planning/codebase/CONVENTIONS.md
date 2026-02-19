# Coding Conventions

**Analysis Date:** 2026-02-19

## Naming Patterns

**Files:**
- Module files use lowercase with underscores: `client.py`, `orchestrator.py`, `reporting.py`
- Python packages use lowercase with underscores: `fk_quant_research_accel`
- Package directory structure mirrors module names exactly

**Functions:**
- Use lowercase with underscores (snake_case): `compute_score()`, `write_csv()`, `generate_black_scholes_scenarios()`
- Private/internal functions prefixed with single underscore: `_parse_int_list()`, `_parse_float_list()`, `_print_top()`
- Public API functions exported in `__all__` from package init

**Variables:**
- Lowercase with underscores: `base_url`, `poll_seconds`, `max_wait_seconds`, `training_config`
- Constant-like values (module-level set) use UPPERCASE: `TERMINAL_STATUSES`
- Dataclass fields use lowercase with underscores: `simulation_id`, `grad_norm`, `train_loss`

**Types:**
- Use dataclasses for structured data: `@dataclass` decorator with frozen=True for immutability
- Type hints are comprehensive and mandatory on all public functions
- Use `from __future__ import annotations` for forward references and modern syntax

## Code Style

**Formatting:**
- Line length: 100 characters (configured in `pyproject.toml`)
- Configured tool: Ruff (linter and formatter)
- Enforce with: `ruff check src tests` in CI pipeline

**Linting:**
- Tool: Ruff
- Configuration: `.planning/codebase/` with `line-length = 100` and `target-version = "py310"`
- Runs in CI on every push and pull request
- All code must pass `ruff check` before merge

**Language version:**
- Minimum Python: 3.10
- Target version: 3.10 (configured in `pyproject.toml`)
- Requires-python: >=3.10 in `pyproject.toml`

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first, enables PEP 563)
2. Standard library imports (`time`, `csv`, `pathlib`, `argparse`, `itertools`, `dataclasses`, `typing`)
3. Third-party imports (`requests`)
4. Local/relative imports from same package (`.client`, `.orchestrator`, `.reporting`)

**Path Aliases:**
- No aliases configured; use relative imports within package
- Example: `from .client import FKPinnClient`

**Import Style:**
- Absolute imports preferred for package exports: `from fk_quant_research_accel.orchestrator import`
- Relative imports within module: `from .client import`
- Batch imports for multiple items on single line only when reasonable (2-3 items)

## Error Handling

**Patterns:**
- Explicit exceptions raised for expected error conditions
- Use `TimeoutError` for polling/wait timeouts (see `client.py:68`)
- Use `response.raise_for_status()` for HTTP errors (automatic exception on 4xx/5xx)
- No broad try-except blocks; let exceptions propagate where appropriate
- Errors include descriptive context: `f"Simulation {simulation_id} did not finish within timeout"`

**HTTP Errors:**
- `requests.get()` and `requests.post()` with `timeout` parameter always set
- `response.raise_for_status()` called immediately after requests
- Timeout defaults: 30 seconds for client operations

## Logging

**Framework:** Python's `print()` and standard output

**Patterns:**
- Use `print()` for CLI output messages (see `cli.py:22-30`)
- Print ranking results with formatted strings: `f"{idx + 1:>2}. score={row['score']:.6f} ..."`
- Include contextual information in print statements (scores, statuses, counts)
- No structured logging or log levels; output is informational only

## Comments

**When to Comment:**
- Module-level docstrings required for all files (one-line description, see `client.py:1`)
- Function docstrings for public API and non-obvious behavior
- Inline comments only for complex logic (minimal in this codebase)

**JSDoc/TSDoc:**
- Not applicable (Python project, not JavaScript)
- Use Python docstrings with triple quotes

**Docstring Style:**
```python
def wait_until_terminal(
    self,
    simulation_id: str,
    poll_seconds: float = 1.5,
    max_wait_seconds: float = 1800.0,
) -> dict[str, Any]:
    """Poll a simulation until it reaches a terminal status or times out."""
```

Pattern: Brief one-liner describing what function does, no parameter/return documentation needed when types are clear.

## Function Design

**Size:** Functions are concise and focused
- Longest function: `run_batch()` at ~45 lines (orchestrates multiple steps logically)
- Most functions: 10-20 lines
- Aim for single responsibility

**Parameters:**
- Use keyword arguments for clarity in callers, especially with multiple similar types
- Example: `run_batch(client=client, scenarios=scenarios, batch_config=config, poll_seconds=..., max_wait_seconds=...)`
- Default parameters used for optional configuration: `poll_seconds: float = 1.5`

**Return Values:**
- Explicitly type-hinted on all public functions: `-> dict[str, Any]`, `-> list[Scenario]`, `-> Path`
- Return built-in types and dataclasses, never bare tuples
- Return `None` implicitly (don't type-hint void functions)

**Dataclass Methods:**
- Conversion methods named with `as_*` or `to_*` pattern: `as_parameters()`, `to_payload()`
- These methods bridge between domain models and API payloads

## Module Design

**Exports:**
- Explicit `__all__` list in package `__init__.py` defining public API
- See `src/fk_quant_research_accel/__init__.py:6-12` for example
- Only export top-level functions and classes meant for external use

**Module Structure:**
- `client.py`: HTTP client abstraction (FKPinnClient class)
- `orchestrator.py`: Domain models (Scenario, BatchConfig) and batch coordination (run_batch)
- `reporting.py`: Output formatting and metric computation (compute_score, write_csv)
- `cli.py`: Argument parsing and CLI entrypoint

**Dataclass Patterns:**
- Use `@dataclass(frozen=True)` for immutable value objects
- Example: `Scenario` and `BatchConfig` are frozen dataclasses
- Methods on dataclasses for conversion: `as_parameters()`, `to_payload()`

---

*Convention analysis: 2026-02-19*
