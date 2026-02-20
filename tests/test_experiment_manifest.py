from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fk_quant_research_accel.models.experiment import ExperimentManifest, load_manifest
from fk_quant_research_accel.models.hashing import content_hash


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


def test_content_hash_deterministic() -> None:
    manifest = ExperimentManifest.model_validate(_minimal_manifest_dict())

    first = content_hash(manifest)
    second = content_hash(manifest)

    assert first == second


def test_content_hash_changes_on_any_field() -> None:
    base = ExperimentManifest.model_validate(_minimal_manifest_dict())
    renamed = base.model_copy(update={"name": "experiment-a"})

    updated_grid = base.scenario_grid.model_copy(update={"volatilities": [0.25]})
    with_changed_vol = base.model_copy(update={"scenario_grid": updated_grid})

    updated_sweep = base.model_sweep.model_copy(update={"architectures": ["mlp"]})
    with_changed_architecture = base.model_copy(update={"model_sweep": updated_sweep})

    base_hash = content_hash(base)
    assert content_hash(renamed) != base_hash
    assert content_hash(with_changed_vol) != base_hash
    assert content_hash(with_changed_architecture) != base_hash


def test_content_hash_ignores_yaml_formatting(tmp_path: Path) -> None:
    compact_path = tmp_path / "compact.yaml"
    spaced_path = tmp_path / "spaced.yaml"

    compact_path.write_text(
        "backend_url: http://localhost:8000\n"
        "scenario_grid: {dimensions: [5], volatilities: [0.2], correlations: [0.0]}\n",
        encoding="utf-8",
    )
    spaced_path.write_text(
        "backend_url: http://localhost:8000\n"
        "scenario_grid:\n"
        "  dimensions:\n"
        "    - 5\n"
        "  volatilities:\n"
        "    - 0.2\n"
        "  correlations:\n"
        "    - 0.0\n",
        encoding="utf-8",
    )

    compact_manifest = load_manifest(compact_path)
    spaced_manifest = load_manifest(spaced_path)

    assert content_hash(compact_manifest) == content_hash(spaced_manifest)


def test_model_sweep_config() -> None:
    payload = _minimal_manifest_dict()
    payload["model_sweep"] = {
        "architectures": ["default", "resmlp"],
        "hidden_sizes": [[64, 64], [128, 128]],
        "activations": ["tanh", "gelu"],
        "optimizers": ["adam", "adamw"],
    }

    manifest = ExperimentManifest.model_validate(payload)

    assert manifest.model_sweep.architectures == ["default", "resmlp"]
    assert manifest.model_sweep.hidden_sizes == [[64, 64], [128, 128]]
    assert manifest.model_sweep.activations == ["tanh", "gelu"]
    assert manifest.model_sweep.optimizers == ["adam", "adamw"]
