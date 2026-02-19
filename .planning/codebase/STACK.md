# Technology Stack

**Analysis Date:** 2026-02-19

## Languages

**Primary:**
- Python 3.10+ - Core language for research orchestration and client logic

**Secondary:**
- YAML - CI/CD workflow configuration

## Runtime

**Environment:**
- Python 3.10+ (project requirement in `pyproject.toml`)
- CPython (runtime agnostic but tested on ubuntu-latest in CI)

**Package Manager:**
- pip (via setuptools)
- Lockfile: Missing (relies on `pyproject.toml` with version constraints)

## Frameworks

**Core:**
- setuptools 68+ - Package build and distribution system

**Testing:**
- pytest 8.0.0+ - Test runner and assertion framework
- pytest integration via `pytest.ini_options` in `pyproject.toml` with `pythonpath = ["src"]`

**Code Quality:**
- ruff 0.6.0+ - Fast Python linter and formatter
- mypy 1.10.0+ - Static type checker

**Build/Dev:**
- GitHub Actions - CI/CD pipeline defined in `.github/workflows/ci.yml`

## Key Dependencies

**Critical:**
- requests 2.32.0+ - HTTP client library for communicating with Feynman-Kac PINN backend
  - Used in `src/fk_quant_research_accel/client.py` for GET/POST requests to `/api/v1/` endpoints
  - Handles JSON serialization, timeouts (default 30s), and HTTP error raising

**Development Only:**
- pytest 8.0.0+ - Test execution and discovery
- ruff 0.6.0+ - Linting and code formatting
- mypy 1.10.0+ - Type checking

## Configuration

**Environment:**
- No `.env` files used - configuration passed via CLI arguments
- FK PINN backend URL must be provided as `--base-url` argument to CLI

**Build:**
- `pyproject.toml` - Single source of truth for project metadata, dependencies, and tool configuration
  - setuptools configuration specifies `src` as package directory
  - ruff configured with 100 character line length, target Python 3.10
  - pytest configured to add `src` to Python path for imports

**Code Style:**
- Line length: 100 characters (ruff configuration in `pyproject.toml`)
- Target version: Python 3.10

## Platform Requirements

**Development:**
- Python 3.10+ installed
- pip package manager
- Virtual environment (`.venv/` directory in gitignore)

**Production:**
- Python 3.10+ runtime
- requests library available
- Network access to Feynman-Kac PINN backend service
- Writable filesystem for CSV output artifacts (`artifacts/` directory)

**CI/CD:**
- GitHub Actions runner (ubuntu-latest)
- Python 3.11 for testing
- pip and setuptools available in environment

---

*Stack analysis: 2026-02-19*
