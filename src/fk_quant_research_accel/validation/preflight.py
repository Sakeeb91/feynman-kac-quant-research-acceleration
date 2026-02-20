"""Manifest pre-flight validation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fk_quant_research_accel.models.experiment import ExperimentManifest


@dataclass(frozen=True)
class PreflightError:
    field: str
    value: Any
    message: str


def validate_manifest(manifest: ExperimentManifest) -> list[PreflightError]:
    del manifest
    return []
