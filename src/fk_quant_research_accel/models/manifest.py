"""Manifest models and reproducibility capture for batch runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ManifestMetadata(BaseModel, frozen=True):
    manifest_schema_version: int = 1
    result_schema_version: int = 1
    db_migration_version: int = 1


class ReproducibilityInfo(BaseModel, frozen=True):
    git_sha: str | None = None
    git_dirty: bool | None = None
    python_version: str
    os_info: str
    seed: int | None = None
    packages: dict[str, str] = Field(default_factory=dict)


class RunManifest(BaseModel, frozen=True):
    batch_run_id: str
    created_at: datetime
    schema_versions: ManifestMetadata = Field(default_factory=ManifestMetadata)
    reproducibility: ReproducibilityInfo
    batch_config: dict[str, Any]
    scenarios: list[dict[str, Any]]
    backend_url: str
