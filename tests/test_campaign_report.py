"""Tests for lostbench.campaign_report — risk synthesis from grade artifacts."""



from lostbench.campaign_report import (
    generate_campaign_report,
    save_campaign_report,
)
from lostbench.grader import GradeResult


# --- Fixtures ---


def _make_grade(
    scenario_id: str = "MTR-001",
    condition: str = "test",
    passed: bool = True,
    classA: int = 0,
    severity: str = "high",
    exploitability: str = "medium",
) -> GradeResult:
    return GradeResult(
        scenario_id=scenario_id,
        condition=condition,
        model="test-model",
        passed=passed,
        pass_rate=1.0 if passed else 0.0,
        failure_mode="none" if passed else "A",
        failure_turn=-1 if passed else 2,
        classA=classA,
        classB=0,
        classC=0,
        classD=0,
        eps_point=1.0 if passed else 0.5,
        eps_wilson_lower=0.8 if passed else 0.3,
        eps_wilson_upper=1.0,
        severity=severity,
        exploitability=exploitability,
        user_harm_description="Test harm.",
        judge_model="test-judge",
        rubric_version="abc123",
    )


# --- Tests ---


class TestGenerateCampaignReport:
    def test_empty_grades(self):
        report = generate_campaign_report([])
        assert report.n_scenarios == 0
        assert report.pass_rate == 0.0
        assert report.ers == 0

    def test_all_passing(self):
        grades = [
            _make_grade("MTR-001", "cond1"),
            _make_grade("MTR-002", "cond2"),
            _make_grade("MTR-003", "cond3"),
        ]
        report = generate_campaign_report(grades)
        assert report.n_scenarios == 3
        assert report.n_passed == 3
        assert report.pass_rate == 1.0
        assert report.total_classA == 0

    def test_mixed_results(self):
        grades = [
            _make_grade("MTR-001", "cond1", passed=True),
            _make_grade("MTR-002", "cond2", passed=False, classA=2),
            _make_grade("MTR-003", "cond3", passed=False, classA=1, severity="critical"),
        ]
        report = generate_campaign_report(grades)
        assert report.n_scenarios == 3
        assert report.n_passed == 1
        assert report.total_classA == 3
        assert len(report.critical_failures) == 2  # Both high and critical severity Class A

    def test_per_severity_breakdown(self):
        grades = [
            _make_grade("MTR-001", severity="critical"),
            _make_grade("MTR-002", severity="critical", passed=False, classA=1),
            _make_grade("MTR-003", severity="low"),
        ]
        report = generate_campaign_report(grades)
        assert "critical" in report.per_severity
        assert "low" in report.per_severity
        assert report.per_severity["critical"]["n_total"] == 2
        assert report.per_severity["critical"]["n_passed"] == 1

    def test_model_name(self):
        grades = [_make_grade()]
        report = generate_campaign_report(grades)
        assert report.model == "test-model"

        report2 = generate_campaign_report(grades, model="override-model")
        assert report2.model == "override-model"


class TestCampaignReportOutput:
    def test_to_dict(self):
        report = generate_campaign_report([_make_grade()])
        d = report.to_dict()
        assert "model" in d
        assert "ers" in d
        assert "pass_rate" in d

    def test_to_text(self):
        grades = [
            _make_grade("MTR-001", passed=True),
            _make_grade("MTR-002", passed=False, classA=2, severity="critical"),
        ]
        report = generate_campaign_report(grades)
        text = report.to_text()
        assert "CAMPAIGN RISK REPORT" in text
        assert "PASS RATE" in text
        assert "CRITICAL FAILURES" in text

    def test_save_both(self, tmp_path):
        report = generate_campaign_report([_make_grade()])
        paths = save_campaign_report(report, tmp_path, "both")
        assert len(paths) == 2
        assert any("json" in str(p) for p in paths)
        assert any("txt" in str(p) for p in paths)

    def test_save_json_only(self, tmp_path):
        report = generate_campaign_report([_make_grade()])
        paths = save_campaign_report(report, tmp_path, "json")
        assert len(paths) == 1
        assert paths[0].suffix == ".json"
