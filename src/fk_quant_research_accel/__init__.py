"""Research acceleration utilities for Feynman-Kac PINN workflows."""

from .client import FKPinnClient
from .orchestrator import (
    BatchConfig,
    Scenario,
    generate_black_scholes_scenarios,
    generate_scenarios_from_manifest,
    run_batch,
)

__all__ = [
    "FKPinnClient",
    "BatchConfig",
    "Scenario",
    "generate_black_scholes_scenarios",
    "generate_scenarios_from_manifest",
    "run_batch",
]
