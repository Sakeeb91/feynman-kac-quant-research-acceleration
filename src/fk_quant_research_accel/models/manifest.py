"""Manifest models and reproducibility capture for batch runs."""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
import yaml


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


def write_manifest(manifest: RunManifest, artifact_dir: Path) -> Path:
    target_dir = artifact_dir / manifest.batch_run_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "manifest.yaml"
    tmp_target = target.with_suffix(".yaml.tmp")

    data = manifest.model_dump(mode="json")
    rendered = yaml.safe_dump(data, default_flow_style=False, sort_keys=True)
    tmp_target.write_text(rendered, encoding="utf-8")
    tmp_target.replace(target)
    return target


def capture_git_info(repo_path: str = ".") -> tuple[str | None, bool | None]:
    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None, None

    return git_sha, bool(porcelain)


def capture_environment() -> dict[str, Any]:
    packages: dict[str, str] = {}
    for dist in importlib_metadata.distributions():
        name = dist.metadata.get("Name")
        if not name:
            continue
        packages[name] = dist.version

    return {
        "python_version": sys.version.split()[0],
        "os_info": platform.platform(),
        "packages": packages,
    }
