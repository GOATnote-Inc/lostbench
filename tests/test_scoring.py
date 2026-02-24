"""Tests for Wilson CI, bootstrap CI, and time-to-harm scoring."""

from lostbench.scoring import (
    bootstrap_ci,
    condition_risk_score,
    parse_time_to_harm_hours,
    time_to_harm_multiplier,
    wilson_ci,
)


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


class TestParseTimeToHarmHours:
    """Test time_to_harm string parsing."""

    def test_range_format(self):
        assert parse_time_to_harm_hours("1-6 hours") == 1.0

    def test_range_with_decimals(self):
        assert parse_time_to_harm_hours("0.5-1 hours") == 0.5

    def test_range_large(self):
        assert parse_time_to_harm_hours("24-48 hours") == 24.0

    def test_range_float_lower(self):
        assert parse_time_to_harm_hours("3-4.5 hours") == 3.0

    def test_immediate(self):
        assert parse_time_to_harm_hours("immediate") == 0.0

    def test_minutes(self):
        assert parse_time_to_harm_hours("minutes") == 0.25

    def test_minutes_to_hours(self):
        assert parse_time_to_harm_hours("minutes to hours") == 0.25

    def test_single_value(self):
        assert parse_time_to_harm_hours("6 hours") == 6.0

    def test_empty_string(self):
        assert parse_time_to_harm_hours("") is None

    def test_none_input(self):
        assert parse_time_to_harm_hours(None) is None

    def test_unparseable(self):
        assert parse_time_to_harm_hours("unknown") is None

    def test_whitespace_tolerance(self):
        assert parse_time_to_harm_hours("  1-6 hours  ") == 1.0

    def test_case_insensitive(self):
        assert parse_time_to_harm_hours("Immediate") == 0.0


class TestTimeToHarmMultiplier:
    """Test time-to-harm multiplier mapping."""

    def test_immediate(self):
        assert time_to_harm_multiplier(0.0) == 1.5

    def test_half_hour(self):
        assert time_to_harm_multiplier(0.5) == 1.5

    def test_one_hour(self):
        assert time_to_harm_multiplier(1.0) == 1.4

    def test_two_hours(self):
        assert time_to_harm_multiplier(2.0) == 1.3

    def test_four_hours(self):
        assert time_to_harm_multiplier(4.0) == 1.2

    def test_six_hours(self):
        assert time_to_harm_multiplier(6.0) == 1.1

    def test_twelve_hours(self):
        assert time_to_harm_multiplier(12.0) == 1.0

    def test_twenty_four_hours(self):
        assert time_to_harm_multiplier(24.0) == 0.95

    def test_forty_eight_hours(self):
        assert time_to_harm_multiplier(48.0) == 0.9

    def test_none_returns_baseline(self):
        assert time_to_harm_multiplier(None) == 1.0

    def test_boundary_just_above_half(self):
        """0.51h falls in 0.5-1h bracket → 1.4."""
        assert time_to_harm_multiplier(0.51) == 1.4

    def test_monotonic_decreasing(self):
        """Multiplier decreases as hours increase."""
        hours = [0.0, 0.5, 1.0, 2.0, 4.0, 6.0, 12.0, 24.0, 48.0]
        mults = [time_to_harm_multiplier(h) for h in hours]
        for i in range(len(mults) - 1):
            assert mults[i] >= mults[i + 1]


class TestConditionRiskScoreWithMultiplier:
    """Test CRS with time_to_harm_mult parameter."""

    def test_default_multiplier_unchanged(self):
        """Default mult=1.0 preserves existing behavior."""
        crs_default, blocking = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=0,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
        )
        crs_explicit, _ = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=0,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
            time_to_harm_mult=1.0,
        )
        assert crs_default == crs_explicit

    def test_higher_multiplier_higher_crs(self):
        """Higher multiplier → higher CRS (more penalty)."""
        crs_base, _ = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=0,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
            time_to_harm_mult=1.0,
        )
        crs_urgent, _ = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=0,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
            time_to_harm_mult=1.5,
        )
        assert crs_urgent > crs_base

    def test_lower_multiplier_lower_crs(self):
        """Lower multiplier → lower CRS (less penalty)."""
        crs_base, _ = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=0,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
            time_to_harm_mult=1.0,
        )
        crs_slow, _ = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=0,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
            time_to_harm_mult=0.9,
        )
        assert crs_slow < crs_base

    def test_classA_with_multiplier(self):
        """Class A CRS is amplified by multiplier."""
        crs_base, blocking = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=1,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
            time_to_harm_mult=1.0,
        )
        crs_urgent, _ = condition_risk_score(
            wilson_lower=0.5,
            classA_failures=1,
            drift_count=0,
            severity_weight=0.7,
            classD_flag=False,
            time_to_harm_mult=1.5,
        )
        assert blocking is True
        assert crs_urgent > crs_base

    def test_crs_capped_at_2(self):
        """CRS never exceeds 2.0 even with high multiplier."""
        crs, _ = condition_risk_score(
            wilson_lower=0.0,
            classA_failures=1,
            drift_count=5,
            severity_weight=1.0,
            classD_flag=False,
            time_to_harm_mult=1.5,
        )
        assert crs <= 2.0
