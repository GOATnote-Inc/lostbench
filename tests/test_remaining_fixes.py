"""Tests for remaining fixes: contamination math, report formats, placeholder guard, judge params."""

import json
import math

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
