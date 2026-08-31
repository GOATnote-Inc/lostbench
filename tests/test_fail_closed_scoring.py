"""Fail-closed scoring regression tests (issue #3).

Missing evidence must never count as successful evidence:
- ``compute_scenario_pass_k`` refuses empty, partial, overfull, or malformed
  trial lists instead of letting ``all([])`` vacuously pass.
- ``--pattern-only`` emergency grading returns ungraded verdicts that are
  excluded from pass^k and surfaced as ungraded counts, never "safe".
- Malformed or overfull checkpoint data refuses to resume.
"""

import asyncio

import pytest

from lostbench.config import RunConfig
from lostbench.report import print_summary
from lostbench.runner import Runner
from lostbench.scoring import IncompleteTrialsError, compute_scenario_pass_k

from conftest import MockProvider


class TestComputeScenarioPassKFailClosed:
    """Regression tests from issue #3: incomplete trials never pass."""

    def test_empty_trial_list_raises(self):
        """all([]) is True in Python; an empty trial list must never pass."""
        with pytest.raises(IncompleteTrialsError):
            compute_scenario_pass_k([], expected_trials=3)

    def test_partial_trial_list_raises(self):
        with pytest.raises(IncompleteTrialsError):
            compute_scenario_pass_k([True, True], expected_trials=3)

    def test_overfull_trial_list_raises(self):
        with pytest.raises(IncompleteTrialsError):
            compute_scenario_pass_k([True, True, True, True], expected_trials=3)

    def test_malformed_trial_results_raise(self):
        with pytest.raises(IncompleteTrialsError):
            compute_scenario_pass_k([True, None, True], expected_trials=3)
        with pytest.raises(IncompleteTrialsError):
            compute_scenario_pass_k([True, 1, True], expected_trials=3)

    def test_invalid_expected_trials_raises(self):
        with pytest.raises(ValueError):
            compute_scenario_pass_k([True], expected_trials=0)

    def test_complete_trials_preserve_strict_and(self):
        """A complete k-trial scenario keeps all-trials-must-pass behavior."""
        assert compute_scenario_pass_k([True, True, True], expected_trials=3) is True
        assert compute_scenario_pass_k([True, False, True], expected_trials=3) is False
        assert (
            compute_scenario_pass_k([False, False, False], expected_trials=3) is False
        )

    def test_incomplete_error_is_value_error(self):
        """IncompleteTrialsError participates in existing ValueError handling."""
        assert issubclass(IncompleteTrialsError, ValueError)


def _pattern_only_runner(trials: int = 1, output_dir: str = ".") -> Runner:
    mock = MockProvider()
    config = RunConfig(
        model="test-model",
        provider="openai",
        corpus="emergency",
        trials=trials,
        conditions=["MTR-001"],
        pattern_only=True,
        output_dir=output_dir,
    )
    return Runner(config, provider=mock, judge_provider=mock, cache_enabled=False)


class TestPatternOnlyEmergencyIsUngraded:
    """--pattern-only emergency grading must never fabricate 'safe' verdicts."""

    def test_grade_response_returns_ungraded_not_safe(self):
        runner = _pattern_only_runner()
        verdict = asyncio.run(
            runner._grade_response("Waiting until morning is fine.", turn=2)
        )
        assert verdict["verdict"] == "ungraded"
        assert verdict["verdict"] != "safe"

    def test_scenario_trials_report_ungraded_counts(self, sample_scenario):
        runner = _pattern_only_runner(trials=2)
        result = asyncio.run(runner._run_scenario_trials(sample_scenario))
        assert result["pass_k"] is None, "ungraded scenario must not pass"
        assert result["trials_expected"] == 2
        assert result["trials_completed"] == 2
        assert result["trials_missing"] == 0
        assert result["trials_ungraded"] == 2
        assert result["trials_passed"] == 0
        assert all(p is None for p in result["per_trial_passed"])

    def test_full_run_excludes_ungraded_from_pass_k(self, tmp_path):
        runner = _pattern_only_runner(output_dir=str(tmp_path))
        results = asyncio.run(runner.run())
        agg = results["aggregate"]
        assert agg["pass_k"] is None, (
            "a pattern-only emergency run must not report a pass rate"
        )
        assert agg["ungraded_scenarios"] == 1
        assert agg["graded_scenarios"] == 0
        assert agg["total_scenarios"] == 1

    def test_print_summary_surfaces_ungraded(self, tmp_path, capsys):
        runner = _pattern_only_runner(output_dir=str(tmp_path))
        results = asyncio.run(runner.run())
        print_summary(results)
        out = capsys.readouterr().out
        assert "UNGRADED" in out
        assert "WARNING" in out


class TestCheckpointResumeFailClosed:
    """Malformed resumed checkpoint data must refuse, not score (issue #3)."""

    def test_overfull_checkpoint_refuses(self, sample_scenario):
        runner = _pattern_only_runner(trials=1)
        prior = [
            {"trial": 0, "passed": True, "per_turn_verdicts": []},
            {"trial": 1, "passed": True, "per_turn_verdicts": []},
        ]
        with pytest.raises(IncompleteTrialsError):
            asyncio.run(
                runner._run_scenario_trials(sample_scenario, prior_trials=prior)
            )

    def test_malformed_checkpoint_trial_refuses(self, sample_scenario):
        runner = _pattern_only_runner(trials=2)
        prior = [{"trial": 0}]  # missing 'passed'
        with pytest.raises(IncompleteTrialsError):
            asyncio.run(
                runner._run_scenario_trials(sample_scenario, prior_trials=prior)
            )
