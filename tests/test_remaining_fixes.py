"""Tests for remaining fixes: contamination math, report formats, placeholder guard, judge params."""

import json
import math
from pathlib import Path

import pytest

from lostbench.contamination import _chi_squared_approximation
from lostbench.report import format_markdown, format_csv


class TestChiSquaredApproximation:
    """Chi-squared fallback must produce correct p-values."""

    def test_equal_rates_high_p(self):
        """Equal pass rates in both groups -> p near 1.0."""
        p = _chi_squared_approximation(50, 50, 50, 50)
        assert p >= 0.4  # Not significant

    def test_large_difference_low_p(self):
        """Large difference -> low p-value."""
        # 90/100 pass vs 50/100 pass
        p = _chi_squared_approximation(90, 10, 50, 50)
        assert p < 0.001

    def test_all_pass_one_group(self):
        """One group all pass, other half -> significant."""
        p = _chi_squared_approximation(20, 0, 10, 10)
        assert p < 0.05

    def test_zero_totals(self):
        """Edge case: no data."""
        p = _chi_squared_approximation(0, 0, 0, 0)
        assert p == 1.0

    def test_one_empty_row(self):
        """One group has no data."""
        p = _chi_squared_approximation(0, 0, 5, 5)
        assert p == 1.0

    def test_erfc_formula_matches_scipy(self):
        """Verify erfc(sqrt(chi2/2)) matches known chi-squared CDF values.

        For chi2 with df=1:
          chi2=3.84 -> p~0.05  (critical value at alpha=0.05)
          chi2=6.63 -> p~0.01
        """
        # chi2=3.84 is the 0.05 critical value for df=1
        p_two_sided = math.erfc(math.sqrt(3.84 / 2))
        assert abs(p_two_sided - 0.05) < 0.005

        # chi2=6.63 is the 0.01 critical value for df=1
        p_two_sided = math.erfc(math.sqrt(6.63 / 2))
        assert abs(p_two_sided - 0.01) < 0.002

    def test_direction_matters(self):
        """Higher published rate returns lower p (one-sided)."""
        # Published higher
        p_higher = _chi_squared_approximation(80, 20, 40, 60)
        # Published lower
        p_lower = _chi_squared_approximation(40, 60, 80, 20)
        assert p_higher < p_lower


class TestFormatMarkdown:
    """Markdown report formatting."""

    def _make_results(self):
        return {
            "aggregate": {
                "pass_k": 0.750,
                "wilson_ci_95": [0.5, 0.9],
                "bootstrap_ci_95": [0.5, 0.95],
                "total_scenarios": 10,
                "total_trials": 30,
            },
            "metadata": {
                "model": "test-model",
                "provider": "openai",
                "judge_model": "claude-opus-4-6",
                "corpus": "emergency",
                "mode": "benchmark",
            },
        }

    def test_contains_header(self):
        md = format_markdown(self._make_results())
        assert "# LostBench Results" in md

    def test_contains_pass_k(self):
        md = format_markdown(self._make_results())
        assert "0.750" in md

    def test_contains_model(self):
        md = format_markdown(self._make_results())
        assert "test-model" in md

    def test_table_format(self):
        md = format_markdown(self._make_results())
        assert "| Metric | Value |" in md
        assert "|--------|-------|" in md

    def test_failure_modes_included(self):
        results = self._make_results()
        results["aggregate"]["per_failure_mode"] = {
            "urgency_minimized": {"count": 3, "rate": 0.3},
        }
        md = format_markdown(results)
        assert "urgency_minimized" in md
        assert "## Failure Modes" in md


class TestFormatCSV:
    """CSV report formatting."""

    def test_csv_header(self):
        results = {"scenarios": []}
        csv_out = format_csv(results)
        assert "scenario_id,pass_k,trials_run,trials_passed" in csv_out

    def test_csv_rows(self):
        results = {
            "scenarios": [
                {"scenario_id": "MTR-001", "pass_k": True, "trials_run": 3, "trials_passed": 3},
                {"scenario_id": "MTR-002", "pass_k": False, "trials_run": 3, "trials_passed": 1},
            ],
        }
        csv_out = format_csv(results)
        assert "MTR-001" in csv_out
        assert "MTR-002" in csv_out
        lines = csv_out.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows


class TestPlaceholderPromptGuard:
    """Placeholder prompts must raise, not silently pass through."""

    def test_placeholder_raises(self, tmp_path):
        placeholder = tmp_path / "placeholder.txt"
        placeholder.write_text("PLACEHOLDER — to be filled before release.")
        from lostbench.config import RunConfig

        config = RunConfig(
            model="test-model",
            provider="openai",
            system_prompt_path=str(placeholder),
        )
        with pytest.raises(ValueError, match="placeholder"):
            _ = config.system_prompt

    def test_normal_prompt_works(self, tmp_path):
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text("You are a helpful medical assistant.")
        from lostbench.config import RunConfig

        config = RunConfig(
            model="test-model",
            provider="openai",
            system_prompt_path=str(prompt_file),
        )
        assert config.system_prompt == "You are a helpful medical assistant."


class TestJudgeExplicitParams:
    """Judge call must explicitly pass temperature and seed."""

    @pytest.mark.asyncio
    async def test_judge_passes_temp_and_seed(self):
        """call_judge passes temperature=0.0 and seed=42 to provider."""
        from lostbench.judge import call_judge

        calls = []

        class CapturingProvider:
            async def chat(self, messages, model=None, temperature=0.0, seed=42):
                calls.append({"temperature": temperature, "seed": seed})
                return '{"maintained": true, "confidence": 0.9, "reasoning": "ok"}'

        provider = CapturingProvider()
        await call_judge(
            provider, "test response", "unknown", "test-judge",
        )
        assert len(calls) == 1
        assert calls[0]["temperature"] == 0.0
        assert calls[0]["seed"] == 42


class TestReportCommand:
    """CLI report command with format options."""

    def _make_results_file(self, tmp_path):
        results = {
            "aggregate": {
                "pass_k": 0.500,
                "wilson_ci_95": [0.3, 0.7],
                "bootstrap_ci_95": [0.3, 0.7],
                "total_scenarios": 4,
                "total_trials": 12,
            },
            "metadata": {
                "model": "test",
                "provider": "openai",
                "judge_model": "claude-opus-4-6",
                "corpus": "emergency",
                "mode": "benchmark",
            },
            "scenarios": [
                {"scenario_id": "MTR-001", "pass_k": True, "trials_run": 3, "trials_passed": 3},
            ],
        }
        path = tmp_path / "results.json"
        path.write_text(json.dumps(results))
        return str(path)

    def test_report_text(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        path = self._make_results_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["report", path])
        assert result.exit_code == 0
        assert "Pass^k" in result.output

    def test_report_markdown(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        path = self._make_results_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["report", "--format", "markdown", path])
        assert result.exit_code == 0
        assert "# LostBench Results" in result.output

    def test_report_csv(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        path = self._make_results_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["report", "--format", "csv", path])
        assert result.exit_code == 0
        assert "scenario_id" in result.output
        assert "MTR-001" in result.output

    def test_report_json(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        path = self._make_results_file(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["report", "--format", "json", path])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["aggregate"]["pass_k"] == 0.500


class TestAnthropicSeedReporting:
    """Anthropic provider must report supports_seed=False."""

    def test_anthropic_class_has_seed_override(self):
        from lostbench.providers.anthropic import AnthropicProvider

        assert "supports_seed" in AnthropicProvider.__dict__

    def test_anthropic_supports_seed_false(self):
        from lostbench.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.supports_seed is False


class TestConfigValidation:
    """RunConfig.validate() checks constraints."""

    def test_trials_less_than_1(self):
        from lostbench.config import RunConfig

        config = RunConfig(model="test-model", provider="openai", trials=0)
        with pytest.raises(SystemExit, match="trials must be >= 1"):
            config.validate()

    def test_temperature_too_high(self):
        from lostbench.config import RunConfig

        config = RunConfig(model="test-model", provider="openai", temperature=3.0)
        with pytest.raises(SystemExit, match="temperature must be in"):
            config.validate()

    def test_temperature_negative(self):
        from lostbench.config import RunConfig

        config = RunConfig(model="test-model", provider="openai", temperature=-0.1)
        with pytest.raises(SystemExit, match="temperature must be in"):
            config.validate()

    def test_valid_config_passes(self):
        from lostbench.config import RunConfig

        config = RunConfig(model="test-model", provider="openai", trials=3, temperature=0.0)
        config.validate()  # Should not raise


class TestReportDefensiveKeys:
    """Report functions handle missing keys gracefully."""

    def test_missing_aggregate_key(self):
        from lostbench.report import print_summary

        with pytest.raises(ValueError, match="missing required key"):
            print_summary({"metadata": {}})

    def test_missing_metadata_key(self):
        from lostbench.report import format_markdown

        with pytest.raises(ValueError, match="missing required key"):
            format_markdown({"aggregate": {}})


class TestCLIContamination:
    """CLI contamination command integration tests."""

    def _make_results(self, tmp_path, filename, items):
        path = tmp_path / filename
        path.write_text(json.dumps(items))
        return str(path)

    def test_contamination_clean(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        # Similar pass rates → no contamination flag
        published = [
            {"scenario_id": f"PUB-{i:03d}", "scenario_source": "published",
             "model_id": "test", "passed": i % 2 == 0}
            for i in range(20)
        ]
        novel = [
            {"scenario_id": f"NOV-{i:03d}", "scenario_source": "novel",
             "model_id": "test", "passed": i % 2 == 0}
            for i in range(20)
        ]
        pub_path = self._make_results(tmp_path, "published.json", published)
        nov_path = self._make_results(tmp_path, "novel.json", novel)

        runner = CliRunner()
        result = runner.invoke(main, ["contamination", pub_path, nov_path])
        assert result.exit_code == 0
        assert "Contamination" in result.output

    def test_contamination_flagged(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        # Published all pass, novel all fail → contamination flagged
        published = [
            {"scenario_id": f"PUB-{i:03d}", "scenario_source": "published",
             "model_id": "test", "passed": True}
            for i in range(20)
        ]
        novel = [
            {"scenario_id": f"NOV-{i:03d}", "scenario_source": "novel",
             "model_id": "test", "passed": False}
            for i in range(20)
        ]
        pub_path = self._make_results(tmp_path, "published.json", published)
        nov_path = self._make_results(tmp_path, "novel.json", novel)

        runner = CliRunner()
        result = runner.invoke(main, ["contamination", pub_path, nov_path])
        assert result.exit_code == 0
        assert "YES" in result.output

    def test_contamination_with_output(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        published = [
            {"scenario_id": f"PUB-{i:03d}", "scenario_source": "published",
             "model_id": "test", "passed": True}
            for i in range(10)
        ]
        novel = [
            {"scenario_id": f"NOV-{i:03d}", "scenario_source": "novel",
             "model_id": "test", "passed": True}
            for i in range(10)
        ]
        pub_path = self._make_results(tmp_path, "published.json", published)
        nov_path = self._make_results(tmp_path, "novel.json", novel)
        out_path = str(tmp_path / "report.json")

        runner = CliRunner()
        result = runner.invoke(main, [
            "contamination", pub_path, nov_path, "--output", out_path,
        ])
        assert result.exit_code == 0
        with open(out_path) as f:
            report_data = json.load(f)
        assert "contamination_flag" in report_data


class TestCLICompare:
    """CLI compare command integration tests."""

    def _make_results_file(self, tmp_path, filename, pass_k, mode="benchmark"):
        results = {
            "aggregate": {
                "pass_k": pass_k,
                "wilson_ci_95": [0.1, 0.9],
                "bootstrap_ci_95": [0.1, 0.9],
                "total_scenarios": 4,
                "total_trials": 12,
            },
            "metadata": {
                "model": "test-model",
                "provider": "openai",
                "judge_model": "claude-opus-4-6",
                "corpus": "emergency",
                "mode": mode,
            },
            "scenarios": [
                {"scenario_id": "MTR-001", "pass_k": True, "trials_run": 3, "trials_passed": 3},
                {"scenario_id": "MTR-002", "pass_k": False, "trials_run": 3, "trials_passed": 1},
            ],
        }
        path = tmp_path / filename
        path.write_text(json.dumps(results))
        return str(path)

    def test_compare_runs(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        base = self._make_results_file(tmp_path, "baseline.json", 0.5)
        comp = self._make_results_file(tmp_path, "comparison.json", 0.75, mode="wrapper")

        runner = CliRunner()
        result = runner.invoke(main, ["compare", base, comp])
        assert result.exit_code == 0
        assert "Pass^k" in result.output
        assert "MTR-001" in result.output

    def test_compare_shows_delta(self, tmp_path):
        from click.testing import CliRunner
        from lostbench.cli import main

        base = self._make_results_file(tmp_path, "baseline.json", 0.5)
        comp = self._make_results_file(tmp_path, "comparison.json", 0.75)

        runner = CliRunner()
        result = runner.invoke(main, ["compare", base, comp])
        assert result.exit_code == 0
        assert "+0.250" in result.output


class TestValidateJudgeFailClosed:
    """validate_judge.py parse_verdict must be fail-closed."""

    def test_no_json_returns_unsafe(self):
        # Import from the script
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_judge",
            str(Path(__file__).resolve().parent.parent / "scripts" / "validate_judge.py"),
            submodule_search_locations=[],
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        verdict = mod.parse_verdict("no json here at all")
        assert verdict.semantic_safe is False
        assert verdict.judge_error is True

    def test_invalid_json_returns_unsafe(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_judge",
            str(Path(__file__).resolve().parent.parent / "scripts" / "validate_judge.py"),
            submodule_search_locations=[],
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        verdict = mod.parse_verdict("{bad json")
        assert verdict.semantic_safe is False
        assert verdict.judge_error is True

    def test_missing_semantic_safe_returns_unsafe(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_judge",
            str(Path(__file__).resolve().parent.parent / "scripts" / "validate_judge.py"),
            submodule_search_locations=[],
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        verdict = mod.parse_verdict('{"confidence": 0.9}')
        assert verdict.semantic_safe is False
        assert verdict.judge_error is True

    def test_valid_json_parses_correctly(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "validate_judge",
            str(Path(__file__).resolve().parent.parent / "scripts" / "validate_judge.py"),
            submodule_search_locations=[],
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        verdict = mod.parse_verdict(
            '{"semantic_safe": true, "violation_turns": [], "violation_types": [], "confidence": 0.95}'
        )
        assert verdict.semantic_safe is True
        assert verdict.judge_error is False
        assert verdict.confidence == 0.95
