"""Tests for CEIS report generation — JSON artifact, executive summary, reproducibility bundle."""

import json

from lostbench.ceis import CorpusGrade, RegressionResult, ScenarioGrade
from lostbench.ceis_config import CEISConfig
from lostbench.ceis_report import (
    format_run_log_entry,
    generate_ceis_json,
    generate_executive_summary,
    generate_reproducibility_bundle,
)


def _make_scenario(
    scenario_id="MTR-001",
    condition="stemi",
    severity_weight=1.0,
    eps_point=1.0,
    eps_wilson_lower=0.75,
    eps_wilson_upper=1.0,
    n_required_turns=5,
    n_maintained_turns=5,
    drift_count=0,
    classA=0,
    classB=0,
    classC=0,
    classD=0,
    passed=True,
) -> ScenarioGrade:
    return ScenarioGrade(
        scenario_id=scenario_id,
        condition=condition,
        severity_weight=severity_weight,
        required_escalation_level=3,
        initial_escalation_correct=True,
        eps_point=eps_point,
        eps_wilson_lower=eps_wilson_lower,
        eps_wilson_upper=eps_wilson_upper,
        n_required_turns=n_required_turns,
        n_maintained_turns=n_maintained_turns,
        drift_count=drift_count,
        classA=classA,
        classB=classB,
        classC=classC,
        classD=classD,
        passed=passed,
    )


def _make_corpus(
    conditions=None,
    ers=85,
    pass_k=0.9,
    harm_weighted_pass=0.88,
    meets_threshold=True,
) -> CorpusGrade:
    if conditions is None:
        conditions = [_make_scenario(), _make_scenario(scenario_id="MTR-002", condition="sepsis")]
    return CorpusGrade(
        ers=ers,
        ers_bootstrap_ci=(78.0, 92.0),
        pass_k=pass_k,
        harm_weighted_pass=harm_weighted_pass,
        total_classA=sum(c.classA for c in conditions),
        total_classB=sum(c.classB for c in conditions),
        total_classC=sum(c.classC for c in conditions),
        total_classD=sum(c.classD for c in conditions),
        total_drift=sum(c.drift_count for c in conditions),
        meets_threshold=meets_threshold,
        threshold_failures=[],
        conditions=conditions,
        grading_metadata={"grading_version": "3-layer-hybrid"},
    )


def _make_config(**overrides) -> CEISConfig:
    defaults = dict(model="gpt-5.2", provider="openai", n_trials=3, corpus="emergency")
    defaults.update(overrides)
    return CEISConfig(**defaults)


class TestGenerateCEISJson:
    """JSON artifact generation per spec Section 12.1."""

    def test_meta_section(self):
        config = _make_config()
        corpus = _make_corpus()
        result = generate_ceis_json(config, corpus, run_id="EG-test-001")

        assert result["meta"]["ceis_version"] == "0.2"
        assert result["meta"]["model_id"] == "gpt-5.2"
        assert result["meta"]["provider"] == "openai"
        assert result["meta"]["temperature"] == 0.0
        assert result["meta"]["seed"] == 42
        assert result["meta"]["n_trials"] == 3
        assert result["meta"]["run_id"] == "EG-test-001"
        assert result["meta"]["n_scenarios"] == 2
        assert "timestamp" in result["meta"]

    def test_aggregate_section(self):
        corpus = _make_corpus(ers=85, pass_k=0.9, harm_weighted_pass=0.88)
        config = _make_config()
        result = generate_ceis_json(config, corpus, run_id="EG-test-002")

        agg = result["aggregate"]
        assert agg["ERS"] == 85
        assert agg["pass_k"] == 0.9
        assert agg["harm_weighted_pass"] == 0.88
        assert agg["meets_threshold"] is True
        assert agg["ERS_bootstrap_ci"] == [78.0, 92.0]
        assert agg["total_classA_failures"] == 0

    def test_conditions_section(self):
        config = _make_config()
        corpus = _make_corpus()
        result = generate_ceis_json(config, corpus, run_id="EG-test-003")

        assert len(result["conditions"]) == 2
        c0 = result["conditions"][0]
        assert c0["scenario_id"] == "MTR-001"
        assert c0["condition"] == "stemi"
        assert c0["severity_weight"] == 1.0
        assert c0["eps_point"] == 1.0
        assert c0["passed"] is True
        assert "crs" in c0

    def test_no_regression(self):
        config = _make_config()
        corpus = _make_corpus()
        result = generate_ceis_json(config, corpus)
        assert "regression" not in result

    def test_with_regression(self):
        config = _make_config()
        corpus = _make_corpus()
        reg = RegressionResult(
            prior_model_id="gpt-5.1",
            prior_ers=90,
            ers_delta=-5,
            regression_detected=False,
            per_condition_z={"MTR-001": 0.5},
            regressed_conditions=[],
            new_classA_conditions=[],
            regression_suite_failures=[],
        )
        result = generate_ceis_json(config, corpus, reg, run_id="EG-test-004")

        assert "regression" in result
        assert result["regression"]["prior_model_id"] == "gpt-5.1"
        assert result["regression"]["prior_ers"] == 90
        assert result["regression"]["ers_delta"] == -5
        assert result["regression"]["regression_detected"] is False

    def test_grading_metadata_preserved(self):
        config = _make_config()
        corpus = _make_corpus()
        result = generate_ceis_json(config, corpus)
        assert result["grading_metadata"]["grading_version"] == "3-layer-hybrid"

    def test_auto_generated_run_id(self):
        config = _make_config()
        corpus = _make_corpus()
        result = generate_ceis_json(config, corpus)
        assert result["meta"]["run_id"].startswith("EG-gpt-5.2-")

    def test_system_prompt_hash_included(self):
        config = _make_config()
        corpus = _make_corpus()
        result = generate_ceis_json(
            config, corpus, run_id="EG-test",
            system_prompt_hash="sha256:abc123",
        )
        assert result["meta"]["system_prompt_hash"] == "sha256:abc123"

    def test_corpus_hash_included(self):
        config = _make_config()
        corpus = _make_corpus()
        result = generate_ceis_json(
            config, corpus, run_id="EG-test",
            corpus_hash="sha256:deadbeef",
        )
        assert result["meta"]["corpus_hash"] == "sha256:deadbeef"

    def test_failure_classes_counted(self):
        conditions = [
            _make_scenario(classA=2, classB=1, classD=1, passed=False),
        ]
        corpus = _make_corpus(conditions=conditions, ers=40, meets_threshold=False)
        config = _make_config()
        result = generate_ceis_json(config, corpus)

        assert result["aggregate"]["total_classA_failures"] == 2
        assert result["aggregate"]["total_classB_failures"] == 1
        assert result["aggregate"]["total_classD_failures"] == 1


class TestGenerateExecutiveSummary:
    """Executive summary text generation per spec Section 12.2."""

    def test_header(self):
        config = _make_config()
        corpus = _make_corpus()
        summary = generate_executive_summary(config, corpus, run_id="EG-test-001")

        assert "ESCALATION PERSISTENCE REPORT" in summary
        assert "gpt-5.2" in summary
        assert "EG-test-001" in summary

    def test_ers_and_ci(self):
        config = _make_config()
        corpus = _make_corpus(ers=85)
        summary = generate_executive_summary(config, corpus, run_id="EG-test")

        assert "85 / 100" in summary
        assert "CI:" in summary

    def test_threshold_meets(self):
        config = _make_config()
        corpus = _make_corpus(meets_threshold=True)
        summary = generate_executive_summary(config, corpus, run_id="EG-test")

        assert "Meets" in summary

    def test_threshold_fails(self):
        config = _make_config()
        conditions = [
            _make_scenario(classA=3, passed=False),
        ]
        corpus_with_failures = CorpusGrade(
            ers=40,
            ers_bootstrap_ci=(30.0, 50.0),
            pass_k=0.0,
            harm_weighted_pass=0.0,
            total_classA=3,
            total_classB=0,
            total_classC=0,
            total_classD=0,
            total_drift=0,
            meets_threshold=False,
            threshold_failures=["ERS below 70", "Class A > 0"],
            conditions=conditions,
        )
        summary = generate_executive_summary(config, corpus_with_failures, run_id="EG-test")

        assert "Does Not Meet" in summary
        assert "ERS below 70" in summary

    def test_no_regression(self):
        config = _make_config()
        corpus = _make_corpus()
        summary = generate_executive_summary(config, corpus, run_id="EG-test")

        assert "No prior version provided" in summary

    def test_regression_detected(self):
        config = _make_config()
        corpus = _make_corpus(ers=60, meets_threshold=False)
        reg = RegressionResult(
            prior_model_id="gpt-5.1",
            prior_ers=90,
            ers_delta=-30,
            regression_detected=True,
            per_condition_z={"MTR-001": -2.5},
            regressed_conditions=["MTR-001"],
            new_classA_conditions=["MTR-001"],
            regression_suite_failures=[],
        )
        summary = generate_executive_summary(config, corpus, reg, run_id="EG-test")

        assert "Detected" in summary
        assert "gpt-5.1" in summary
        assert "REGRESSION DETAIL" in summary
        assert "MTR-001" in summary

    def test_methodology_section(self):
        config = _make_config(n_trials=5)
        corpus = _make_corpus()
        summary = generate_executive_summary(config, corpus, run_id="EG-test")

        assert "METHODOLOGY:" in summary
        assert "5 trials" in summary
        assert "Wilson" in summary
        assert "bootstrap" in summary

    def test_key_metrics_section(self):
        config = _make_config()
        corpus = _make_corpus(pass_k=0.9, harm_weighted_pass=0.88)
        summary = generate_executive_summary(config, corpus, run_id="EG-test")

        assert "KEY METRICS:" in summary
        assert "0.900" in summary
        assert "0.880" in summary

    def test_failed_conditions_listed(self):
        config = _make_config()
        conditions = [
            _make_scenario(
                scenario_id="MTR-001", condition="stemi",
                classA=2, classB=1, passed=False,
            ),
            _make_scenario(scenario_id="MTR-002", condition="sepsis"),
        ]
        corpus = _make_corpus(conditions=conditions, meets_threshold=False)
        summary = generate_executive_summary(config, corpus, run_id="EG-test")

        assert "CONDITIONS BELOW THRESHOLD:" in summary
        assert "stemi" in summary
        assert "Class A x2" in summary


class TestReproducibilityBundle:
    """Reproducibility bundle generation per spec Section 10.4."""

    def test_bundle_directory_structure(self, tmp_path):
        config = _make_config()
        corpus = _make_corpus()
        artifact = generate_ceis_json(config, corpus, run_id="EG-test-bundle")

        bundle_dir = generate_reproducibility_bundle(
            tmp_path, config, artifact, run_id="EG-test-bundle",
        )

        assert bundle_dir.exists()
        assert (bundle_dir / "config.yaml").exists()
        assert (bundle_dir / "config_hash.sha256").exists()
        assert (bundle_dir / "corpus_hash.sha256").exists()
        assert (bundle_dir / "results.json").exists()
        assert (bundle_dir / "report.txt").exists()

    def test_results_json_valid(self, tmp_path):
        config = _make_config()
        corpus = _make_corpus()
        artifact = generate_ceis_json(config, corpus, run_id="EG-test-bundle")

        bundle_dir = generate_reproducibility_bundle(
            tmp_path, config, artifact, run_id="EG-test-bundle",
        )

        with open(bundle_dir / "results.json") as f:
            loaded = json.load(f)
        assert loaded["meta"]["run_id"] == "EG-test-bundle"
        assert loaded["aggregate"]["ERS"] == 85

    def test_config_yaml_no_secrets(self, tmp_path):
        import yaml

        config = _make_config()
        corpus = _make_corpus()
        artifact = generate_ceis_json(config, corpus, run_id="EG-test-bundle")

        bundle_dir = generate_reproducibility_bundle(
            tmp_path, config, artifact, run_id="EG-test-bundle",
        )

        config_yaml = yaml.safe_load((bundle_dir / "config.yaml").read_text())
        assert config_yaml["model"] == "gpt-5.2"
        assert config_yaml["provider"] == "openai"
        assert "api_key" not in config_yaml
        assert "OPENAI_API_KEY" not in str(config_yaml)

    def test_config_hash_deterministic(self, tmp_path):
        config = _make_config()
        corpus = _make_corpus()
        artifact = generate_ceis_json(config, corpus, run_id="EG-test-bundle")

        bundle_dir = generate_reproducibility_bundle(
            tmp_path, config, artifact, run_id="EG-test-bundle",
        )

        hash_content = (bundle_dir / "config_hash.sha256").read_text().strip()
        assert hash_content.startswith("sha256:")
        assert len(hash_content) > 10

    def test_report_txt_generated(self, tmp_path):
        config = _make_config()
        corpus = _make_corpus()
        artifact = generate_ceis_json(config, corpus, run_id="EG-test-bundle")

        bundle_dir = generate_reproducibility_bundle(
            tmp_path, config, artifact, run_id="EG-test-bundle",
        )

        report = (bundle_dir / "report.txt").read_text()
        assert "ESCALATION PERSISTENCE REPORT" in report
        assert "gpt-5.2" in report

    def test_run_id_from_artifact(self, tmp_path):
        config = _make_config()
        corpus = _make_corpus()
        artifact = generate_ceis_json(config, corpus, run_id="EG-auto-id")

        bundle_dir = generate_reproducibility_bundle(tmp_path, config, artifact)
        assert bundle_dir.name == "EG-auto-id"


class TestFormatRunLogEntry:
    """Run log JSONL formatting per spec Section 12.3."""

    def test_basic_entry(self):
        config = _make_config()
        corpus = _make_corpus(ers=85, pass_k=0.9, harm_weighted_pass=0.88)
        entry_str = format_run_log_entry(config, corpus, run_id="EG-test-log")

        entry = json.loads(entry_str)
        assert entry["id"] == "EG-test-log"
        assert entry["task"] == "ceis"
        assert entry["models"] == ["gpt-5.2"]
        assert entry["scorer"] == "3-layer-hybrid"
        assert entry["n_scenarios"] == 2
        assert entry["n_trials"] == 3
        assert entry["seed"] == 42
        assert entry["results"]["gpt-5.2"]["ERS"] == 85
        assert entry["results"]["gpt-5.2"]["pass_k"] == 0.9

    def test_single_line(self):
        config = _make_config()
        corpus = _make_corpus()
        entry_str = format_run_log_entry(config, corpus, run_id="EG-test")
        assert "\n" not in entry_str

    def test_with_regression(self):
        config = _make_config()
        corpus = _make_corpus()
        reg = RegressionResult(
            prior_model_id="gpt-5.1",
            prior_ers=90,
            ers_delta=-5,
            regression_detected=True,
            per_condition_z={},
            regressed_conditions=[],
            new_classA_conditions=[],
            regression_suite_failures=[],
        )
        entry_str = format_run_log_entry(config, corpus, reg, run_id="EG-test")
        entry = json.loads(entry_str)
        assert entry["results"]["gpt-5.2"]["regression_detected"] is True

    def test_no_regression(self):
        config = _make_config()
        corpus = _make_corpus()
        entry_str = format_run_log_entry(config, corpus, run_id="EG-test")
        entry = json.loads(entry_str)
        assert entry["results"]["gpt-5.2"]["regression_detected"] is None

    def test_notes_and_artifacts_dir(self):
        config = _make_config()
        corpus = _make_corpus()
        entry_str = format_run_log_entry(
            config, corpus, run_id="EG-test",
            artifacts_dir="/tmp/results",
            notes="initial run",
        )
        entry = json.loads(entry_str)
        assert entry["artifacts_dir"] == "/tmp/results"
        assert entry["notes"] == "initial run"

    def test_auto_generated_run_id(self):
        config = _make_config()
        corpus = _make_corpus()
        entry_str = format_run_log_entry(config, corpus)
        entry = json.loads(entry_str)
        assert entry["id"].startswith("EG-gpt-5.2-")

    def test_timestamp_present(self):
        config = _make_config()
        corpus = _make_corpus()
        entry_str = format_run_log_entry(config, corpus, run_id="EG-test")
        entry = json.loads(entry_str)
        assert "ts" in entry
        assert "T" in entry["ts"]  # ISO format
