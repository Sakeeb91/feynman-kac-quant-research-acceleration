from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fk_quant_research_accel.models.experiment import ExperimentManifest, load_manifest


def _minimal_manifest_dict() -> dict[str, object]:
    return {
        "backend_url": "http://localhost:8000",
        "scenario_grid": {
            "dimensions": [5],
            "volatilities": [0.2],
            "correlations": [0.0],
        },
    }


def test_load_manifest_from_dict() -> None:
    manifest = ExperimentManifest.model_validate(_minimal_manifest_dict())

    assert manifest.backend_url == "http://localhost:8000"
    assert manifest.scenario_grid.dimensions == [5]
    assert manifest.scenario_grid.volatilities == [0.2]
    assert manifest.scenario_grid.correlations == [0.0]


def test_load_manifest_from_yaml_file(tmp_path: Path) -> None:
    target = tmp_path / "experiment.yaml"
    target.write_text(
        """
backend_url: http://localhost:8000
scenario_grid:
  dimensions: [5]
  volatilities: [0.2]
  correlations: [0.0]
""".strip(),
        encoding="utf-8",
    )

    manifest = load_manifest(target)

    assert manifest.backend_url == "http://localhost:8000"
    assert manifest.scenario_grid.dimensions == [5]


def test_manifest_requires_backend_url() -> None:
    payload = _minimal_manifest_dict()
    payload.pop("backend_url")

    with pytest.raises(ValidationError):
        ExperimentManifest.model_validate(payload)


def test_manifest_requires_scenario_grid() -> None:
    payload = _minimal_manifest_dict()
    payload.pop("scenario_grid")

    with pytest.raises(ValidationError):
        ExperimentManifest.model_validate(payload)


def test_manifest_defaults() -> None:
    manifest = ExperimentManifest.model_validate(_minimal_manifest_dict())

    assert manifest.model_sweep.architectures == ["default"]
    assert manifest.batch_config.n_steps == 40
    assert manifest.batch_config.batch_size == 64
    assert manifest.batch_config.n_mc_paths == 256
    assert manifest.batch_config.learning_rate == pytest.approx(1e-3)
    assert manifest.scoring.strategy == "loss_based"
    assert manifest.scoring.grad_norm_weight == pytest.approx(0.01)
    assert manifest.output.artifacts_dir == "artifacts"
    assert manifest.output.db_path is None


def test_manifest_frozen() -> None:
    manifest = ExperimentManifest.model_validate(_minimal_manifest_dict())

    with pytest.raises(ValidationError):
        manifest.backend_url = "http://127.0.0.1:9000"  # type: ignore[misc]
