"""Tests for pass^k calculation."""


from lostbench.scoring import (
    compute_scenario_pass_k,
    compute_aggregate_pass_k,
    compute_aggregate_scores,
)


class TestPassKCalculation:
    """3 scenarios, 3 trials, known pass/fail matrix → verify aggregate matches formula exactly."""

    def test_all_pass(self):
        """All scenarios, all trials pass → pass_k = 1.0"""
        # 3 scenarios, each with 3 passing trials
        scenario_pass_k = [
            compute_scenario_pass_k([True, True, True]),  # True
            compute_scenario_pass_k([True, True, True]),  # True
            compute_scenario_pass_k([True, True, True]),  # True
        ]
        assert all(scenario_pass_k)
        assert compute_aggregate_pass_k(scenario_pass_k) == 1.0

    def test_all_fail(self):
        """All scenarios have at least one failing trial → pass_k = 0.0"""
        scenario_pass_k = [
            compute_scenario_pass_k([False, True, True]),  # False (one fail)
            compute_scenario_pass_k([True, False, True]),  # False
            compute_scenario_pass_k([False, False, False]),  # False
        ]
        assert not any(scenario_pass_k)
        assert compute_aggregate_pass_k(scenario_pass_k) == 0.0

    def test_mixed(self):
        """2 of 3 scenarios pass → pass_k = 2/3"""
        scenario_pass_k = [
            compute_scenario_pass_k([True, True, True]),  # True
            compute_scenario_pass_k([True, False, True]),  # False (strict AND)
            compute_scenario_pass_k([True, True, True]),  # True
        ]
        assert scenario_pass_k == [True, False, True]
        result = compute_aggregate_pass_k(scenario_pass_k)
        assert abs(result - 2 / 3) < 1e-10

    def test_strict_and(self):
        """Single failure in any trial → scenario fails."""
        # Even with 2/3 passing, strict AND means fail
        assert compute_scenario_pass_k([True, True, False]) is False
        assert compute_scenario_pass_k([False, True, True]) is False

    def test_single_scenario(self):
        """Single scenario with mixed trials."""
        pk = [compute_scenario_pass_k([True, False, True])]
        assert compute_aggregate_pass_k(pk) == 0.0

    def test_exact_formula(self):
        """Verify formula: pass_k = (1/S) × Σ_s [1 if ALL k trials pass, else 0]"""
        # 3 scenarios: pass, fail, pass → (1/3)(1 + 0 + 1) = 2/3
        scenario_pass_k = [True, False, True]
        expected = (1 / 3) * (1 + 0 + 1)
        actual = compute_aggregate_pass_k(scenario_pass_k)
        assert abs(actual - expected) < 1e-10

    def test_empty_scenarios(self):
        """No scenarios → 0.0"""
        assert compute_aggregate_pass_k([]) == 0.0

    def test_aggregate_scores_integration(self):
        """Full aggregate computation with 3 scenarios."""
        scenario_pass_k = [True, False, True]
        total_trials = 9  # 3 scenarios × 3 trials
        agg = compute_aggregate_scores(scenario_pass_k, total_trials)

        assert abs(agg.pass_k - 2 / 3) < 1e-10
        assert agg.total_scenarios == 3
        assert agg.total_trials == 9
        # Wilson CI should be reasonable
        assert 0.0 <= agg.wilson_ci[0] <= agg.wilson_ci[1] <= 1.0
        # Bootstrap CI should be reasonable
        assert 0.0 <= agg.bootstrap_ci[0] <= agg.bootstrap_ci[1] <= 1.0
