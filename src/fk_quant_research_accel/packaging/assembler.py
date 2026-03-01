"""Assemble self-contained model package directories from run artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
import yaml

from fk_quant_research_accel.store.metadata import MetadataStore

from .acceptance import check_acceptance
from .manifest import ModelPackageManifest, PackageMetrics


class ModelPackager:
    def __init__(self, store: MetadataStore, artifacts_dir: str | Path) -> None:
        self.store = store
        self.artifacts_dir = Path(artifacts_dir)
        self.log = structlog.get_logger()

    def export_package(
        self,
        batch_run_id: str,
        output_dir: str | Path,
        scenario_run_id: str | None = None,
        force: bool = False,
    ) -> Path:
        batch_row = self.store.get_batch_run(batch_run_id)
        if batch_row is None:
            raise ValueError(f"Batch run not found: {batch_run_id}")

        scenario_row = self._select_scenario_row(batch_run_id, scenario_run_id=scenario_run_id)
        selected_scenario_run_id = str(scenario_row["scenario_run_id"])

        training_config = self._parse_json_object(
            batch_row.get("config_json"),
            field_name="batch_runs.config_json",
        )
        scenario_config = self._parse_json_object(
            scenario_row.get("scenario_json"),
            field_name="scenario_runs.scenario_json",
        )
        result_payload = self._parse_json_object(
            scenario_row.get("result_json"),
            field_name="scenario_runs.result_json",
        )

        artifact_manifest = self._read_artifact_manifest(batch_run_id)
        reproducibility = self._build_reproducibility(
            batch_row=batch_row,
            artifact_manifest=artifact_manifest,
        )

        package_dir = Path(output_dir) / (
            f"model_pkg_{batch_run_id[:8]}_{selected_scenario_run_id[:8]}"
        )
        if package_dir.exists():
            if not force:
                raise FileExistsError(f"Package directory already exists: {package_dir}")
            shutil.rmtree(package_dir)

        (package_dir / "checkpoint").mkdir(parents=True, exist_ok=True)
        (package_dir / "config").mkdir(parents=True, exist_ok=True)
        (package_dir / "environment").mkdir(parents=True, exist_ok=True)
        (package_dir / "validation").mkdir(parents=True, exist_ok=True)

        checkpoint_file, checkpoint_sha256 = self._copy_checkpoint(
            package_dir=package_dir,
            checkpoint_path=scenario_row.get("checkpoint_path"),
            scenario_run_id=selected_scenario_run_id,
        )

        metrics_model = PackageMetrics(
            train_loss=self._coerce_float_or_none(result_payload.get("train_loss")),
            val_loss=self._coerce_float_or_none(result_payload.get("val_loss")),
            grad_norm=self._coerce_float_or_none(result_payload.get("grad_norm")),
            score=self._coerce_float_or_none(
                result_payload.get("score", scenario_row.get("score"))
            ),
            convergence_health=(
                str(result_payload.get("convergence_health"))
                if result_payload.get("convergence_health") is not None
                else None
            ),
            progress=self._coerce_float_or_none(result_payload.get("progress")),
        )
        metrics_payload = metrics_model.model_dump(mode="json")

        acceptance = check_acceptance(
            metrics=metrics_payload,
            convergence_health=metrics_model.convergence_health or "",
            checkpoint_path=checkpoint_file,
        )

        self._write_yaml(
            package_dir / "config" / "training_config.yaml",
            training_config,
        )
        self._write_yaml(
            package_dir / "config" / "scenario_config.yaml",
            scenario_config,
        )
        self._write_yaml(
            package_dir / "environment" / "reproducibility.yaml",
            reproducibility,
        )
        if batch_row.get("seed") is not None:
            (package_dir / "environment" / "seed.txt").write_text(
                f"{batch_row['seed']}\n",
                encoding="utf-8",
            )

        self._write_yaml(
            package_dir / "validation" / "metrics.yaml",
            metrics_payload,
        )
        self._write_yaml(
            package_dir / "validation" / "acceptance.yaml",
            acceptance.model_dump(mode="json"),
        )

        readme_body = self._render_readme(
            batch_run_id=batch_run_id,
            scenario_run_id=selected_scenario_run_id,
            problem_id=str(batch_row.get("problem_id") or "black_scholes"),
            score=metrics_model.score,
            convergence_health=metrics_model.convergence_health,
            acceptance_passed=acceptance.passed,
        )
        (package_dir / "README.txt").write_text(readme_body, encoding="utf-8")

        contents = self._collect_contents(package_dir)
        manifest_contents = sorted(set(contents + ["MANIFEST.yaml"]))

        package_manifest = ModelPackageManifest(
            created_at=datetime.now(timezone.utc),
            batch_run_id=batch_run_id,
            scenario_run_id=selected_scenario_run_id,
            problem_id=str(batch_row.get("problem_id") or "black_scholes"),
            checkpoint_file=checkpoint_file,
            checkpoint_sha256=checkpoint_sha256,
            training_config=training_config,
            scenario_config=scenario_config,
            seed=batch_row.get("seed"),
            reproducibility=reproducibility,
            metrics=metrics_model,
            acceptance=acceptance,
            contents=manifest_contents,
        )
        self._write_yaml(
            package_dir / "MANIFEST.yaml",
            package_manifest.model_dump(mode="json"),
        )

        return package_dir

    def _select_scenario_row(
        self,
        batch_run_id: str,
        *,
        scenario_run_id: str | None,
    ) -> dict[str, Any]:
        scenario_rows = self.store.get_scenario_runs(batch_run_id)

        if scenario_run_id is not None:
            for row in scenario_rows:
                if str(row.get("scenario_run_id")) == scenario_run_id:
                    return row
            raise ValueError(
                f"Scenario run '{scenario_run_id}' not found in batch '{batch_run_id}'"
            )

        completed_rows: list[tuple[float, dict[str, Any]]] = []
        for row in scenario_rows:
            if str(row.get("status")) != "completed":
                continue
            score = self._coerce_float_or_none(row.get("score"))
            if score is None or not math.isfinite(score):
                continue
            completed_rows.append((score, row))

        if not completed_rows:
            raise ValueError(
                f"No completed scenarios with finite scores found in batch '{batch_run_id}'"
            )

        return min(completed_rows, key=lambda item: item[0])[1]

    def _read_artifact_manifest(self, batch_run_id: str) -> dict[str, Any]:
        manifest_path = self.artifacts_dir / batch_run_id / "manifest.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Missing batch artifact manifest: {manifest_path}")

        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValueError(f"Expected mapping in manifest YAML: {manifest_path}")
        return payload

    def _build_reproducibility(
        self,
        *,
        batch_row: dict[str, Any],
        artifact_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        reproducibility_obj = artifact_manifest.get("reproducibility")
        reproducibility: dict[str, Any]
        if isinstance(reproducibility_obj, dict):
            reproducibility = dict(reproducibility_obj)
        else:
            reproducibility = {}

        fallback = {
            "git_sha": batch_row.get("git_sha"),
            "git_dirty": bool(batch_row.get("git_dirty"))
            if batch_row.get("git_dirty") is not None
            else None,
            "python_version": batch_row.get("python_version"),
            "os_info": batch_row.get("os_info"),
            "seed": batch_row.get("seed"),
        }
        for key, value in fallback.items():
            if key not in reproducibility and value is not None:
                reproducibility[key] = value

        packages = reproducibility.get("packages")
        if not isinstance(packages, dict):
            reproducibility["packages"] = {}

        return reproducibility

    def _copy_checkpoint(
        self,
        *,
        package_dir: Path,
        checkpoint_path: Any,
        scenario_run_id: str,
    ) -> tuple[str | None, str | None]:
        if checkpoint_path is None:
            return None, None

        source = Path(str(checkpoint_path))
        if not source.exists():
            self.log.warning(
                "checkpoint_missing_during_packaging",
                scenario_run_id=scenario_run_id,
                checkpoint_path=str(source),
            )
            return None, None

        destination = package_dir / "checkpoint" / source.name
        shutil.copy2(source, destination)
        relative_path = str(destination.relative_to(package_dir))
        checksum = self._sha256(destination)
        return relative_path, checksum

    def _parse_json_object(self, raw: Any, *, field_name: str) -> dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        if not isinstance(raw, str):
            raise ValueError(f"Expected JSON string for {field_name}, got {type(raw).__name__}")

        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise ValueError(f"Expected JSON object for {field_name}")
        return loaded

    def _coerce_float_or_none(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _write_yaml(self, path: Path, payload: dict[str, Any]) -> None:
        rendered = yaml.safe_dump(payload, sort_keys=True)
        path.write_text(rendered, encoding="utf-8")

    def _collect_contents(self, package_dir: Path) -> list[str]:
        paths: list[str] = []
        for candidate in package_dir.rglob("*"):
            if candidate.is_file():
                paths.append(str(candidate.relative_to(package_dir)))
        return sorted(paths)

    def _render_readme(
        self,
        *,
        batch_run_id: str,
        scenario_run_id: str,
        problem_id: str,
        score: float | None,
        convergence_health: str | None,
        acceptance_passed: bool,
    ) -> str:
        return "\n".join(
            [
                "Model Package Summary",
                "",
                f"Created at: {datetime.now(timezone.utc).isoformat()}",
                f"Batch run ID: {batch_run_id}",
                f"Scenario run ID: {scenario_run_id}",
                f"Problem ID: {problem_id}",
                f"Score: {score if score is not None else 'n/a'}",
                f"Convergence health: {convergence_health or 'unknown'}",
                f"Acceptance: {'PASSED' if acceptance_passed else 'FAILED'}",
                "",
                "Files:",
                "- MANIFEST.yaml",
                "- checkpoint/",
                "- config/",
                "- environment/",
                "- validation/",
            ]
        )

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
