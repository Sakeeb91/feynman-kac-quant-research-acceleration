"""Filesystem artifact directory management and atomic writers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def create_batch_dir(self, batch_run_id: str) -> Path:
        path = self.root / batch_run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_scenario_dir(self, batch_run_id: str, scenario_run_id: str) -> Path:
        path = self.root / batch_run_id / scenario_run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_scenario_dir(self, batch_run_id: str, scenario_run_id: str) -> Path:
        return self.root / batch_run_id / scenario_run_id

    def atomic_write_json(self, path: Path, data: dict[str, Any]) -> None:
        rendered = json.dumps(data, indent=2, sort_keys=True)
        self.atomic_write_text(path, rendered)

    def atomic_write_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(path)

    def atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
