"""Tests for program self-audit."""

import json

import pytest
import yaml

from lostbench.audit import (
    AuditReport,
    blind_spot_detection,
    calibration_drift_check,
    check_risk_debt,
    run_audit,
)


@pytest.fixture
def audit_fixtures(tmp_path):
    # Taxonomy
    taxonomy = {
        "vectors": [
            {
                "id": "code-agent",
                "corpus_dir": "src/lostbench/scenarios/tier1_codeagent/",
                "conditions_targeted": ["stemi", "neonatal_sepsis", "dka"],
            },
        ],
    }
    taxonomy_path = tmp_path / "taxonomy.yaml"
    with open(taxonomy_path, "w") as f:
        yaml.dump(taxonomy, f)

    # Scenarios
    scenarios_dir = tmp_path / "scenarios"
    ca_dir = scenarios_dir / "tier1_codeagent"
    ca_dir.mkdir(parents=True)
    with open(ca_dir / "CAM-001.yaml", "w") as f:
        yaml.dump({"id": "CAM-001", "condition": "stemi"}, f)
    with open(ca_dir / "CAM-002.yaml", "w") as f:
        yaml.dump({"id": "CAM-002", "condition": "neonatal_sepsis"}, f)

    # Results
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    index = {"experiments": [{"model": "gpt-5.2", "corpus": "code-agent"}]}
    with open(results_dir / "index.yaml", "w") as f:
        yaml.dump(index, f)

    ceis_dir = results_dir / "run1"
    ceis_dir.mkdir()
    ceis_results = {
        "grading_metadata": {
            "total_turns_graded": 50,
            "layer_0_pct": 90.0,
            "layer_2_pct": 10.0,
        },
    }
    with open(ceis_dir / "ceis_results.json", "w") as f:
        json.dump(ceis_results, f)

    # Risk debt
    risk_debt_path = tmp_path / "risk_debt.yaml"
    risk_debt = {
        "accepted_risks": [
            {
                "finding_id": "TEST-001",
                "family_id": "EF-001",
                "severity": "critical",
                "review_date": "2026-01-01",  # Already past
            },
            {
                "finding_id": "TEST-002",
                "family_id": "EF-002",
                "severity": "high",
                "review_date": "2099-12-31",  # Future
            },
        ],
    }
    with open(risk_debt_path, "w") as f:
        yaml.dump(risk_debt, f)

    # Family registry
    family_path = tmp_path / "families.yaml"
    registry = {
        "families": [
            {
                "family_id": "EF-001",
                "persistence": [{"model": "gpt-5.2", "status": "active"}],
            },
            {
                "family_id": "EF-002",
                "persistence": [{"model": "gpt-5.2", "status": "resolved"}],
            },
        ],
    }
    with open(family_path, "w") as f:
        yaml.dump(registry, f)

    return {
        "taxonomy_path": taxonomy_path,
        "scenarios_dir": scenarios_dir,
        "results_dir": results_dir,
        "risk_debt_path": risk_debt_path,
        "family_path": family_path,
    }


def test_blind_spot_detection(audit_fixtures):
    spots = blind_spot_detection(
        audit_fixtures["taxonomy_path"],
        audit_fixtures["scenarios_dir"],
        audit_fixtures["results_dir"],
    )
    # dka has no scenario
    assert any("dka" in s.issue for s in spots)


def test_calibration_drift_check(audit_fixtures):
    metrics = calibration_drift_check(audit_fixtures["results_dir"])
    assert len(metrics) == 1
    assert metrics[0].layer_0_pct == 90.0
    assert metrics[0].total_turns == 50


def test_check_risk_debt(audit_fixtures):
    items = check_risk_debt(audit_fixtures["risk_debt_path"], today="2026-02-24")
    assert len(items) == 2
    overdue = [i for i in items if i.is_overdue]
    assert len(overdue) == 1
    assert overdue[0].finding_id == "TEST-001"


def test_run_audit(audit_fixtures):
    report = run_audit(
        taxonomy_path=audit_fixtures["taxonomy_path"],
        scenarios_dir=audit_fixtures["scenarios_dir"],
        results_dir=audit_fixtures["results_dir"],
        family_registry_path=audit_fixtures["family_path"],
        risk_debt_path=audit_fixtures["risk_debt_path"],
    )
    assert isinstance(report, AuditReport)
    assert report.total_families == 2
    assert report.active_families == 1
    assert report.overdue_risk_count == 1
    text = report.to_text()
    assert "ADVERSARIAL PROGRAM SELF-AUDIT" in text
    assert "dka" in text  # Blind spot
