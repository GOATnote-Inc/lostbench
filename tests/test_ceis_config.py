"""Tests for CEIS configuration loading and CLI subcommands."""

import json

import pytest
import yaml
from click.testing import CliRunner

from lostbench.ceis_config import CEISConfig, load_ceis_config
from lostbench.cli import main


class TestCEISConfig:
    """CEISConfig dataclass validation."""

    def test_minimal_valid_config(self):
        config = CEISConfig(model="gpt-5.2", provider="openai")
        errors = config.validate()
        assert errors == []

    def test_missing_model(self):
        config = CEISConfig(model="", provider="openai")
        errors = config.validate()
        assert any("model" in e for e in errors)

    def test_missing_provider(self):
        config = CEISConfig(model="gpt-5.2", provider="")
        errors = config.validate()
        assert any("provider" in e for e in errors)

    def test_invalid_provider(self):
        config = CEISConfig(model="gpt-5.2", provider="invalid")
        errors = config.validate()
        assert any("provider" in e for e in errors)

    def test_nonzero_temperature_rejected(self):
        config = CEISConfig(model="gpt-5.2", provider="openai", temperature=0.7)
        errors = config.validate()
        assert any("temperature" in e for e in errors)

    def test_invalid_n_trials(self):
        config = CEISConfig(model="gpt-5.2", provider="openai", n_trials=0)
        errors = config.validate()
        assert any("n_trials" in e for e in errors)

    def test_invalid_corpus(self):
        config = CEISConfig(model="gpt-5.2", provider="openai", corpus="invalid")
        errors = config.validate()
        assert any("corpus" in e for e in errors)

    def test_mutually_exclusive_wrapper_preamble(self):
        config = CEISConfig(
            model="gpt-5.2", provider="openai",
            wrapper_enabled=True, inject_preamble=True,
        )
        errors = config.validate()
        assert any("mutually exclusive" in e for e in errors)

    def test_invalid_output_format(self):
        config = CEISConfig(
            model="gpt-5.2", provider="openai",
            output_formats=["json", "pdf"],
        )
        errors = config.validate()
        assert any("pdf" in e for e in errors)

    def test_nonexistent_system_prompt_path(self):
        config = CEISConfig(
            model="gpt-5.2", provider="openai",
            system_prompt_path="/nonexistent/path.txt",
        )
        errors = config.validate()
        assert any("system_prompt_path" in e for e in errors)

    def test_frozen(self):
        config = CEISConfig(model="gpt-5.2", provider="openai")
        with pytest.raises(AttributeError):
            config.model = "changed"


class TestCEISConfigToRunConfig:
    """CEISConfig → RunConfig conversion."""

    def test_basic_conversion(self):
        config = CEISConfig(model="gpt-5.2", provider="openai", n_trials=5)
        rc = config.to_run_config()
        assert rc.model == "gpt-5.2"
        assert rc.provider == "openai"
        assert rc.trials == 5
        assert rc.temperature == 0.0
        assert rc.seed == 42

    def test_wrapper_settings_preserved(self):
        config = CEISConfig(
            model="gpt-5.2", provider="openai",
            wrapper_enabled=True, wrapper_preamble=False,
        )
        rc = config.to_run_config()
        assert rc.wrapper_enabled is True
        assert rc.wrapper_preamble is False

    def test_judge_model_passed_through(self):
        config = CEISConfig(
            model="gpt-5.2", provider="openai",
            judge_model="claude-opus-4-6",
        )
        rc = config.to_run_config()
        assert rc.judge_model == "claude-opus-4-6"

    def test_conditions_passed_through(self):
        config = CEISConfig(
            model="gpt-5.2", provider="openai",
            conditions=["MTR-001", "MTR-008"],
        )
        rc = config.to_run_config()
        assert rc.conditions == ["MTR-001", "MTR-008"]


class TestLoadCEISConfig:
    """YAML config file loading."""

    def test_load_minimal_yaml(self, tmp_path):
        config_path = tmp_path / "ceis.yaml"
        config_path.write_text(yaml.dump({
            "model": "gpt-5.2",
            "provider": "openai",
        }))
        config = load_ceis_config(config_path)
        assert config.model == "gpt-5.2"
        assert config.provider == "openai"
        assert config.n_trials == 3  # default

    def test_load_full_yaml(self, tmp_path):
        config_path = tmp_path / "ceis.yaml"
        config_path.write_text(yaml.dump({
            "model": "claude-opus-4-6",
            "provider": "anthropic",
            "corpus": "emergency",
            "n_trials": 5,
            "judge_model": "gpt-5.2",
            "output_dir": "/tmp/ceis-out",
            "output_formats": ["json", "text"],
            "prior_model_id": "v2.3",
        }))
        config = load_ceis_config(config_path)
        assert config.model == "claude-opus-4-6"
        assert config.n_trials == 5
        assert config.output_formats == ["json", "text"]
        assert config.prior_model_id == "v2.3"

    def test_conditions_as_string(self, tmp_path):
        config_path = tmp_path / "ceis.yaml"
        config_path.write_text(yaml.dump({
            "model": "gpt-5.2",
            "provider": "openai",
            "conditions": "MTR-001, MTR-008",
        }))
        config = load_ceis_config(config_path)
        assert config.conditions == ["MTR-001", "MTR-008"]

    def test_conditions_as_list(self, tmp_path):
        config_path = tmp_path / "ceis.yaml"
        config_path.write_text(yaml.dump({
            "model": "gpt-5.2",
            "provider": "openai",
            "conditions": ["MTR-001", "MTR-008"],
        }))
        config = load_ceis_config(config_path)
        assert config.conditions == ["MTR-001", "MTR-008"]

    def test_output_formats_as_string(self, tmp_path):
        config_path = tmp_path / "ceis.yaml"
        config_path.write_text(yaml.dump({
            "model": "gpt-5.2",
            "provider": "openai",
            "output_formats": "json",
        }))
        config = load_ceis_config(config_path)
        assert config.output_formats == ["json"]

    def test_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_ceis_config("/nonexistent/path.yaml")

    def test_invalid_yaml(self, tmp_path):
        config_path = tmp_path / "bad.yaml"
        config_path.write_text("not: valid: yaml: [")
        with pytest.raises(Exception):
            load_ceis_config(config_path)

    def test_non_dict_yaml(self, tmp_path):
        config_path = tmp_path / "list.yaml"
        config_path.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_ceis_config(config_path)


class TestCEISCLI:
    """CEIS CLI subcommand parsing."""

    def test_ceis_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ceis", "--help"])
        assert result.exit_code == 0
        assert "Clinical Escalation Integrity Suite" in result.output

    def test_ceis_run_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ceis", "run", "--help"])
        assert result.exit_code == 0
        assert "--config" in result.output

    def test_ceis_report_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ceis", "report", "--help"])
        assert result.exit_code == 0
        assert "--results" in result.output
        assert "--format" in result.output

    def test_ceis_run_missing_config(self):
        runner = CliRunner()
        result = runner.invoke(main, ["ceis", "run"])
        assert result.exit_code != 0

    def test_ceis_run_invalid_config(self, tmp_path):
        """Config with missing model → validation error."""
        config_path = tmp_path / "bad.yaml"
        config_path.write_text(yaml.dump({"provider": "openai"}))
        runner = CliRunner()
        result = runner.invoke(main, ["ceis", "run", "--config", str(config_path)])
        assert result.exit_code != 0
        assert "model" in result.output

    def test_ceis_report_json(self, tmp_path):
        """Report command outputs JSON."""
        results_path = tmp_path / "ceis_results.json"
        results_path.write_text(json.dumps({
            "meta": {"model_id": "test-model"},
            "aggregate": {
                "ERS": 75,
                "pass_k": 0.85,
                "harm_weighted_pass": 0.80,
                "meets_threshold": True,
                "total_classA_failures": 0,
                "total_classB_failures": 1,
                "total_drift_events": 2,
            },
        }))
        runner = CliRunner()
        result = runner.invoke(main, [
            "ceis", "report", "--results", str(results_path), "--format", "json",
        ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["aggregate"]["ERS"] == 75

    def test_ceis_report_text(self, tmp_path):
        """Report command outputs text summary."""
        results_path = tmp_path / "ceis_results.json"
        results_path.write_text(json.dumps({
            "meta": {"model_id": "test-model"},
            "aggregate": {
                "ERS": 75,
                "pass_k": 0.85,
                "harm_weighted_pass": 0.80,
                "meets_threshold": True,
                "total_classA_failures": 0,
                "total_classB_failures": 1,
                "total_drift_events": 2,
            },
        }))
        runner = CliRunner()
        result = runner.invoke(main, [
            "ceis", "report", "--results", str(results_path), "--format", "text",
        ])
        assert result.exit_code == 0
        assert "CEIS Evaluation Report" in result.output
        assert "75" in result.output

    def test_ceis_report_with_regression(self, tmp_path):
        """Report command shows regression section if present."""
        results_path = tmp_path / "ceis_results.json"
        results_path.write_text(json.dumps({
            "meta": {"model_id": "test-model"},
            "aggregate": {
                "ERS": 61,
                "pass_k": 0.5,
                "harm_weighted_pass": 0.42,
                "meets_threshold": False,
                "total_classA_failures": 3,
                "total_classB_failures": 5,
                "total_drift_events": 7,
            },
            "regression": {
                "prior_model_id": "v2.3",
                "ers_delta": -13,
                "regression_detected": True,
                "new_classA_conditions": ["aortic_dissection"],
            },
        }))
        runner = CliRunner()
        result = runner.invoke(main, [
            "ceis", "report", "--results", str(results_path), "--format", "text",
        ])
        assert result.exit_code == 0
        assert "Regression" in result.output
        assert "YES" in result.output
        assert "aortic_dissection" in result.output
