"""Tests for coverage heatmap generator."""

import pytest
import yaml

from lostbench.coverage import (
    compute_coverage,
    identify_gaps,
    generate_heatmap_html,
)


@pytest.fixture
def taxonomy_file(tmp_path):
    taxonomy = {
        "taxonomy_id": "test_v1",
        "vectors": [
            {
                "id": "code-agent",
                "corpus_dir": "src/lostbench/scenarios/tier1_codeagent/",
                "scenario_prefix": "CAM",
                "conditions_targeted": ["stemi", "neonatal_sepsis", "dka"],
            },
            {
                "id": "tool-use",
                "corpus_dir": "src/lostbench/scenarios/tier1_tooluse/",
                "scenario_prefix": "TUE",
                "conditions_targeted": ["stemi", "neonatal_sepsis"],
            },
        ],
    }
    path = tmp_path / "taxonomy.yaml"
    with open(path, "w") as f:
        yaml.dump(taxonomy, f)
    return path


@pytest.fixture
def scenarios_dir(tmp_path):
    ca_dir = tmp_path / "tier1_codeagent"
    ca_dir.mkdir()
    for sid, cond in [("CAM-001", "stemi"), ("CAM-002", "neonatal_sepsis")]:
        with open(ca_dir / f"{sid}.yaml", "w") as f:
            yaml.dump({"id": sid, "condition": cond}, f)

    tu_dir = tmp_path / "tier1_tooluse"
    tu_dir.mkdir()
    with open(tu_dir / "TUE-001.yaml", "w") as f:
        yaml.dump({"id": "TUE-001", "condition": "stemi"}, f)

    return tmp_path


def test_compute_coverage(taxonomy_file, scenarios_dir):
    matrix = compute_coverage(taxonomy_file, scenarios_dir)
    assert "code-agent" in matrix.vectors
    assert "tool-use" in matrix.vectors
    # CAM-001 (stemi) and CAM-002 (neonatal_sepsis) exist; dka does not
    assert matrix.scenario_coverage["code-agent"]["stemi"] == "CAM-001"
    assert matrix.scenario_coverage["code-agent"]["dka"] is None


def test_identify_gaps(taxonomy_file, scenarios_dir):
    matrix = compute_coverage(taxonomy_file, scenarios_dir)
    gaps = identify_gaps(matrix)
    # dka has no scenario under code-agent; neonatal_sepsis has no scenario under tool-use
    gap_descriptions = [g.description for g in gaps]
    assert any("dka" in d and "code-agent" in d for d in gap_descriptions)
    assert any("neonatal_sepsis" in d and "tool-use" in d for d in gap_descriptions)


def test_generate_heatmap_html(taxonomy_file, scenarios_dir, tmp_path):
    matrix = compute_coverage(taxonomy_file, scenarios_dir)
    output = tmp_path / "coverage.html"
    generate_heatmap_html(matrix, output)
    assert output.exists()
    content = output.read_text()
    assert "<html>" in content
    assert "stemi" in content
    assert "MISSING" in content  # dka should show as missing
