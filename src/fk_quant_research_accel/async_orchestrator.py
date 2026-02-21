"""Concurrent async orchestrator for durable batch execution."""

from __future__ import annotations

import base64
import json
import random
import time
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from datetime import timezone
from functools import partial
from pathlib import Path
from typing import Any
from typing import TypeVar

import anyio
import httpx
import structlog
from anyio import CapacityLimiter
from anyio import create_task_group
from tenacity import AsyncRetrying
from tenacity import stop_after_attempt
from tenacity import wait_exponential_jitter

from .async_client import AsyncFKPinnClient
from .models import ReproducibilityInfo
from .models import RunManifest
from .models import ScenarioStatus
from .models import capture_environment
from .models import capture_git_info
from .models import generate_batch_run_id
from .models import generate_scenario_run_id
from .models import write_manifest
from .orchestrator import BatchConfig
from .orchestrator import Scenario
from .reporting import compute_score
from .retry import RETRY_DEFAULTS
from .retry import is_retryable_error
from .store import ArtifactStore
from .store import MetadataStore


T = TypeVar("T")
TERMINAL_STATUSES = {
    ScenarioStatus.COMPLETED.value,
    ScenarioStatus.FAILED.value,
    ScenarioStatus.CANCELLED.value,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _known_statuses() -> set[str]:
    return {status.value for status in ScenarioStatus}


def _build_failure_record(
    scenario: Scenario,
    simulation_id: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "simulation_id": simulation_id,
        "status": ScenarioStatus.FAILED.value,
        "dim": scenario.dim,
        "volatility": scenario.volatility,
        "correlation": scenario.correlation,
        "option_type": scenario.option_type,
        "progress": 0.0,
        "train_loss": None,
        "val_loss": None,
        "lr": None,
        "grad_norm": None,
        "score": float("inf"),
        "error_message": error_message,
        "checkpoint_path": None,
    }


async def _run_store(call: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    return await anyio.to_thread.run_sync(partial(call, *args, **kwargs))


async def _fetch_checkpoint(
    simulation_id: str,
    result_item: dict[str, Any],
    scenario_dir: Path,
    artifact_store: ArtifactStore,
) -> Path | None:
    checkpoint_dir = scenario_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "model_checkpoint.pt"
    log = structlog.get_logger().bind(simulation_id=simulation_id)
    _ = (result_item, artifact_store, checkpoint_path, log)
    return None
