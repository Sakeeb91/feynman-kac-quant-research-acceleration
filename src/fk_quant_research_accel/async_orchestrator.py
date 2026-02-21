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
