"""Tests for dashboard generator."""

import json

import pytest
import yaml

from lostbench.dashboard import generate_dashboard


@pytest.fixture
def results_dir(tmp_path):
    # Create index.yaml
    index = {
        "experiments": [
            {
                "experiment": "2x2",
                "model": "gpt-5.2",
                "mode": "baseline",
                "date": "2026-02-19",
                "n_trials": 3,
                "scenarios": 23,
                "pass_k": 0.261,
                "ers": 61,
                "path": "results/2x2/gpt52-baseline/",
            },
            {
                "experiment": "2x2",
                "model": "gpt-5.2",
                "mode": "preamble_only",
                "date": "2026-02-19",
                "n_trials": 3,
                "scenarios": 23,
                "pass_k": 0.696,
                "ers": 70,
                "path": "results/2x2/gpt52-preamble/",
            },
        ]
    }
    with open(tmp_path / "index.yaml", "w") as f:
        yaml.dump(index, f)

    # Create a CEIS results file
    ceis_dir = tmp_path / "2x2" / "gpt52-baseline"
    ceis_dir.mkdir(parents=True)
    ceis_results = {
        "meta": {"model_id": "gpt-5.2", "n_scenarios": 23, "n_trials": 3},
        "aggregate": {
            "ERS": 61,
            "pass_k": 0.261,
            "total_classA_failures": 10,
            "total_classB_failures": 5,
            "total_classC_failures": 3,
            "total_classD_failures": 1,
        },
    }
    with open(ceis_dir / "ceis_results.json", "w") as f:
        json.dump(ceis_results, f)

    return tmp_path


def test_generate_dashboard(results_dir, tmp_path):
    output = tmp_path / "dashboard.html"
    generate_dashboard(results_dir, output)
    assert output.exists()
    content = output.read_text()
    assert "LostBench Adversarial Dashboard" in content
    assert "gpt-5.2" in content
    assert "61" in content  # ERS value


def test_generate_dashboard_empty(tmp_path):
    output = tmp_path / "dashboard.html"
    generate_dashboard(tmp_path, output)
    assert output.exists()
    content = output.read_text()
    assert "0" in content  # Zero experiments
