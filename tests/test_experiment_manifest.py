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
