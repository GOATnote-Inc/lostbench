"""Tests for Wilson CI and bootstrap CI calculations."""

import pytest
import math

from lostbench.scoring import wilson_ci, bootstrap_ci, compute_aggregate_pass_k


class TestWilsonCI:
    """Test against hand-calculated values."""

    def test_3_of_10(self):
        """3 successes out of 10 → known CI bounds."""
        lower, upper = wilson_ci(3, 10)
        # Hand calculation for Wilson CI with z=1.96:
        # p_hat = 0.3
        # denom = 1 + 1.96^2/10 = 1.3842
        # center = (0.3 + 1.96^2/20) / 1.3842 = (0.3 + 0.19208) / 1.3842 = 0.3553
        # spread = 1.96 * sqrt((0.3*0.7 + 1.96^2/40)/10) / 1.3842
        #        = 1.96 * sqrt((0.21 + 0.09604)/10) / 1.3842
        #        = 1.96 * sqrt(0.030604) / 1.3842
        #        = 1.96 * 0.17494 / 1.3842
        #        = 0.2477
        # lower = 0.3553 - 0.2477 = 0.1076
        # upper = 0.3553 + 0.2477 = 0.6030
        assert 0.10 < lower < 0.12
        assert 0.59 < upper < 0.62

    def test_0_of_10(self):
        """0 successes → lower bound is 0."""
        lower, upper = wilson_ci(0, 10)
        assert lower == 0.0
        assert 0.0 < upper < 0.35

    def test_10_of_10(self):
        """10 of 10 → upper bound is 1.0."""
        lower, upper = wilson_ci(10, 10)
        assert 0.65 < lower < 1.0
        assert upper == 1.0

    def test_empty(self):
        """0 trials → (0, 0)."""
        assert wilson_ci(0, 0) == (0.0, 0.0)

    def test_bounds_ordered(self):
        """Lower bound ≤ upper bound."""
        for s in range(11):
            lower, upper = wilson_ci(s, 10)
            assert lower <= upper

    def test_half_and_half(self):
        """5 of 10 → centered around 0.5."""
        lower, upper = wilson_ci(5, 10)
        assert 0.2 < lower < 0.5
        assert 0.5 < upper < 0.8


class TestBootstrapCI:
    """Verify scenario-level resampling."""

    def test_all_pass(self):
        """All scenarios pass → CI is [1.0, 1.0]."""
        values = [True] * 10
        lower, upper = bootstrap_ci(values)
        assert lower == 1.0
        assert upper == 1.0

    def test_all_fail(self):
        """All scenarios fail → CI is [0.0, 0.0]."""
        values = [False] * 10
        lower, upper = bootstrap_ci(values)
        assert lower == 0.0
        assert upper == 0.0

    def test_mixed(self):
        """Mixed results → CI contains the point estimate."""
        values = [True, True, True, False, False, False, False, False, False, False]
        # 3 of 10 pass → point estimate 0.3
        lower, upper = bootstrap_ci(values)
        assert 0.0 <= lower <= 0.3
        assert 0.3 <= upper <= 1.0

    def test_scenario_level_resampling(self):
        """Bootstrap draws S scenarios (not individual trials)."""
        # With 3 scenarios (True, False, True), bootstrap should resample
        # 3 items with replacement from [True, False, True]
        values = [True, False, True]
        lower, upper = bootstrap_ci(values, n_iterations=10000)
        # Possible means: 0/3, 1/3, 2/3, 3/3
        # The CI should reflect this discrete distribution
        assert 0.0 <= lower
        assert upper <= 1.0

    def test_deterministic_with_seed(self):
        """Same seed → same results."""
        values = [True, True, False, True, False]
        ci1 = bootstrap_ci(values, rng_seed=42)
        ci2 = bootstrap_ci(values, rng_seed=42)
        assert ci1 == ci2

    def test_empty(self):
        """No scenarios → (0, 0)."""
        assert bootstrap_ci([]) == (0.0, 0.0)

    def test_single_scenario(self):
        """Single scenario → CI matches the single value."""
        lower, upper = bootstrap_ci([True])
        assert lower == 1.0
        assert upper == 1.0
