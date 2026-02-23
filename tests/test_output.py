"""Tests for output format: pressure type tagging, context aggregation, failure mode aggregation,
transcript storage, limitations field."""

import asyncio

from lostbench.config import RunConfig
from lostbench.runner import Runner, LIMITATIONS

from conftest import MockProvider


def _make_runner_with_mock(responses, corpus="emergency", trials=1, pattern_only=True):
    """Helper to create a runner with mock provider."""
    mock = MockProvider(responses)
    config = RunConfig(
        model="test-model",
        provider="openai",
        corpus=corpus,
        trials=trials,
        pattern_only=pattern_only,
    )
    runner = Runner(config, provider=mock, judge_provider=mock)
    return runner


class TestPressureTypeTagging:
    """Output JSON per_pressure_type aggregates have correct failure rates."""

    def test_pressure_type_aggregation(self, sample_scenario):
        """Pressure type structure present with pattern_only (all-safe, no grading signal)."""
        responses = [
            "Call 911 now.",
            "Call 911 — ERs cannot turn you away.",
            "Call 911 immediately.",
            "Call 911 immediately.",
            "Call 911 and watch for these signs.",
        ]
        runner = _make_runner_with_mock(responses)

        scenario_result = asyncio.run(runner._run_scenario_trials(sample_scenario))
        scenarios = [sample_scenario]
        pressure_types = runner._aggregate_pressure_types([scenario_result], scenarios)

        # pattern_only + emergency = all safe (no grading signal without LLM judge)
        assert "financial_barrier" in pressure_types
        assert pressure_types["financial_barrier"]["failure_rate"] == 0.0
        assert "social_pressure" in pressure_types
        assert pressure_types["social_pressure"]["failure_rate"] == 0.0

    def test_multiple_trials_pressure_aggregation(self, sample_scenario):
        """Multiple trials aggregate pressure type stats."""
        # All safe responses for 2 trials
        all_responses = [
            # Trial 1: all safe
            "Call 911.",
            "Call 911.",
            "Call 911.",
            "Call 911.",
            "Call 911.",
            # Trial 2: all safe
            "Call 911.",
            "Call 911.",
            "Call 911.",
            "Call 911.",
            "Call 911.",
        ]
        mock = MockProvider(all_responses)
        config = RunConfig(
            model="test-model",
            provider="openai",
            trials=2,
            pattern_only=True,
        )
        runner = Runner(config, provider=mock, judge_provider=mock)

        result = asyncio.run(runner._run_scenario_trials(sample_scenario))
        ptypes = runner._aggregate_pressure_types([result], [sample_scenario])

        # 4 pressure types × 2 trials = 8 data points
        total_n = sum(p["n"] for p in ptypes.values())
        assert total_n == 8  # 4 pressure types × 2 trials


class TestContextAggregation:
    """Output JSON per_context aggregates correct."""

    def test_context_aggregation(self, sample_scenario):
        responses = ["Call 911."] * 5
        runner = _make_runner_with_mock(responses)

        result = asyncio.run(runner._run_scenario_trials(sample_scenario))
        contexts = runner._aggregate_by_field([result], [sample_scenario], "context")

        assert "us_urban_insured" in contexts
        assert contexts["us_urban_insured"]["n"] == 1
        assert contexts["us_urban_insured"]["failure_rate"] == 0.0


class TestPerFailureModeAggregation:
    """Output counts by failure mode type are correct."""

    def test_failure_mode_counts(self, sample_scenario):
        """With pattern_only, all emergency verdicts are safe (no grading signal)."""
        responses = [
            "Call 911.",
            "Waiting until morning should be fine.",
            "This is probably fine.",
            "Nothing more I can do.",
            "Call 911.",
        ]
        runner = _make_runner_with_mock(responses)

        result = asyncio.run(runner._run_scenario_trials(sample_scenario))
        fm = runner._aggregate_failure_modes([result])

        # pattern_only + emergency = no failure detection (LLM judge required)
        # With dynamic enumeration, zero-count modes are absent from the dict
        assert fm.get("delay_validated", {}).get("count", 0) == 0
        assert fm.get("urgency_minimized", {}).get("count", 0) == 0
        assert fm.get("patient_abandoned", {}).get("count", 0) == 0
        assert fm.get("unclassified", {}).get("count", 0) == 0

    def test_failure_mode_rates(self, sample_scenario):
        """With pattern_only, all rates are 0 (no grading signal)."""
        responses = [
            "Call 911.",
            "Waiting until morning should be fine.",
            "Call 911.",
            "Call 911.",
            "Call 911.",
        ]
        runner = _make_runner_with_mock(responses)

        result = asyncio.run(runner._run_scenario_trials(sample_scenario))
        fm = runner._aggregate_failure_modes([result])

        assert fm.get("delay_validated", {}).get("count", 0) == 0
        assert fm.get("delay_validated", {}).get("rate", 0.0) == 0.0


class TestTranscriptStorage:
    """Full conversation array present in per-trial output."""

    def test_transcript_present(self, sample_scenario):
        responses = ["Call 911."] * 5
        runner = _make_runner_with_mock(responses)

        result = asyncio.run(runner._run_single_trial(sample_scenario, 0))
        assert "conversation" in result
        conv = result["conversation"]

        # System + (user + assistant) × 5 turns = 11 messages
        assert len(conv) == 11
        assert conv[0]["role"] == "system"
        assert conv[1]["role"] == "user"
        assert conv[2]["role"] == "assistant"

    def test_transcript_content(self, sample_scenario):
        responses = [
            "Response 1",
            "Response 2",
            "Response 3",
            "Response 4",
            "Response 5",
        ]
        runner = _make_runner_with_mock(responses)

        result = asyncio.run(runner._run_single_trial(sample_scenario, 0))
        conv = result["conversation"]

        # Check assistant responses are stored
        assistant_messages = [m for m in conv if m["role"] == "assistant"]
        assert len(assistant_messages) == 5
        assert assistant_messages[0]["content"] == "Response 1"


class TestLimitationsField:
    """Limitations present in every results JSON."""

    def test_limitations_in_emergency_results(self, sample_scenario):
        responses = ["Call 911."] * 5
        runner = _make_runner_with_mock(responses)

        # Run full pipeline
        results = asyncio.run(runner._run_emergency([sample_scenario], "testhash"))
        assert "limitations" in results
        assert results["limitations"] == LIMITATIONS
        assert results["limitations"]["evaluation_type"] == "controlled_synthetic"

    def test_limitations_in_crisis_results(self, sample_crisis_scenario):
        responses = ["Call 988 now."] * 4
        runner = _make_runner_with_mock(responses, corpus="crisis-resource")

        results = asyncio.run(
            runner._run_crisis_resource([sample_crisis_scenario], "testhash")
        )
        assert "limitations" in results
        assert results["limitations"]["evaluation_type"] == "controlled_synthetic"


class TestReproducibilityAnomaly:
    """Divergent trial results flagged with divergent_trial_indices."""

    def test_anomaly_detected_via_aggregation(self):
        """Reproducibility anomaly detected when trial results diverge."""
        # Test the aggregation logic directly (emergency pattern_only = all safe,
        # so we can't trigger anomaly through the runner with pattern_only).
        trial_results = [
            {"first_failure_turn": None},
            {"first_failure_turn": 2},
            {"first_failure_turn": None},
        ]
        trial_passed_list = [True, False, True]

        agg = Runner._aggregate_trial_results(trial_results, trial_passed_list)

        assert agg["reproducibility_anomaly"] is True
        assert 1 in agg["divergent_trial_indices"]
        assert agg["first_failure_turn"] == 2

    def test_no_anomaly_when_consistent(self, sample_scenario):
        """All trials same result → no anomaly."""
        responses = ["Call 911."] * 15  # 5 turns × 3 trials
        mock = MockProvider(responses)
        config = RunConfig(
            model="test-model",
            provider="openai",
            trials=3,
            pattern_only=True,
        )
        runner = Runner(config, provider=mock, judge_provider=mock)

        result = asyncio.run(runner._run_scenario_trials(sample_scenario))
        assert result["reproducibility_anomaly"] is False
        assert result["divergent_trial_indices"] == []
