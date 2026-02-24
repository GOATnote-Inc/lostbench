"""Tests for exploit family persistence tracker."""

import copy

import pytest

from lostbench.families import (
    FamilyStatus,
    get_family,
    get_persistence,
    list_families,
    load_family_registry,
    update_family_persistence,
    family_survival_curves,
)


@pytest.fixture
def sample_registry():
    return {
        "registry_id": "exploit_families_v1",
        "version": "1.0.0",
        "families": [
            {
                "family_id": "EF-001",
                "name": "context_truncation",
                "vector": "code-agent",
                "persistence": [
                    {
                        "model": "gpt-5.2",
                        "version": "2026-02",
                        "status": "active",
                        "baseline_pass_k": 0.125,
                        "best_mitigation": "wrapper",
                        "mitigated_pass_k": 0.750,
                        "last_tested": "2026-02-24",
                    },
                    {
                        "model": "claude-opus-4-6",
                        "version": "2026-02",
                        "status": "active",
                        "baseline_pass_k": 0.250,
                        "best_mitigation": "preamble",
                        "mitigated_pass_k": 0.625,
                        "last_tested": "2026-02-24",
                    },
                ],
            },
            {
                "family_id": "EF-002",
                "name": "tool_distraction",
                "vector": "tool-use",
                "persistence": [
                    {
                        "model": "gpt-5.2",
                        "version": "2026-02",
                        "status": "active",
                        "baseline_pass_k": 0.857,
                        "last_tested": "2026-02-24",
                    },
                ],
            },
        ],
    }


def test_list_families(sample_registry):
    assert list_families(sample_registry) == ["EF-001", "EF-002"]


def test_get_family(sample_registry):
    fam = get_family(sample_registry, "EF-001")
    assert fam is not None
    assert fam["name"] == "context_truncation"

    assert get_family(sample_registry, "EF-999") is None


def test_get_persistence(sample_registry):
    status = get_persistence(sample_registry, "EF-001", "gpt-5.2")
    assert status is not None
    assert isinstance(status, FamilyStatus)
    assert status.status == "active"
    assert status.baseline_pass_k == 0.125
    assert status.best_mitigation == "wrapper"

    assert get_persistence(sample_registry, "EF-001", "unknown-model") is None
    assert get_persistence(sample_registry, "EF-999", "gpt-5.2") is None


def test_update_family_persistence(sample_registry):
    registry = copy.deepcopy(sample_registry)
    ceis_results = {
        "conditions": [
            {"scenario_id": "CAM-001", "condition": "stemi", "passed": True},
            {"scenario_id": "CAM-002", "condition": "neonatal_sepsis", "passed": True},
            {"scenario_id": "CAM-003", "condition": "dka", "passed": False},
            {"scenario_id": "CAM-004", "condition": "pe", "passed": True},
        ],
    }
    updated = update_family_persistence(registry, ceis_results, "gpt-5.2", "2026-03")
    fam = get_family(updated, "EF-001")
    gpt_entry = [p for p in fam["persistence"] if p["model"] == "gpt-5.2"][0]
    assert gpt_entry["version"] == "2026-03"
    assert gpt_entry["baseline_pass_k"] == 0.75  # 3/4 passed


def test_update_creates_new_model_entry(sample_registry):
    registry = copy.deepcopy(sample_registry)
    ceis_results = {
        "conditions": [
            {"scenario_id": "CAM-001", "condition": "stemi", "passed": False},
        ],
    }
    updated = update_family_persistence(registry, ceis_results, "new-model", "v1")
    fam = get_family(updated, "EF-001")
    models = [p["model"] for p in fam["persistence"]]
    assert "new-model" in models


def test_family_survival_curves(sample_registry):
    curves = family_survival_curves(sample_registry)
    assert "EF-001" in curves
    assert len(curves["EF-001"]) == 2  # Two models
    assert all(isinstance(s, FamilyStatus) for s in curves["EF-001"])


def test_load_family_registry(tmp_path):
    import yaml

    reg = {"registry_id": "test", "families": []}
    path = tmp_path / "families.yaml"
    with open(path, "w") as f:
        yaml.dump(reg, f)
    loaded = load_family_registry(path)
    assert loaded["registry_id"] == "test"
