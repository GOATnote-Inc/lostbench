"""Scoring functions for LostBench — pass^k, Wilson CI, bootstrap CI."""

import math
import random
from dataclasses import dataclass


@dataclass
class AggregateScore:
    pass_k: float
    total_scenarios: int
    total_trials: int
    wilson_ci: tuple[float, float]
    bootstrap_ci: tuple[float, float]


def compute_scenario_pass_k(trial_results: list[bool]) -> bool:
    """Strict AND across all trials for a single scenario."""
    return all(trial_results)


def compute_aggregate_pass_k(scenario_pass_k_values: list[bool]) -> float:
    """Average of per-scenario pass_k booleans.

    pass_k = (1/S) * sum_s[1 if ALL k trials of s passed, else 0]
    """
    if not scenario_pass_k_values:
        return 0.0
    return sum(scenario_pass_k_values) / len(scenario_pass_k_values)


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    p_hat = successes / n
    denominator = 1 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denominator
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n) / denominator
    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (lower, upper)


def bootstrap_ci(
    scenario_pass_k_values: list[bool],
    n_iterations: int = 10_000,
    ci_percentiles: tuple[float, float] = (2.5, 97.5),
    rng_seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap CI by resampling at the SCENARIO level.

    Each iteration draws S scenarios with replacement.
    Reports [2.5th, 97.5th] percentiles.
    """
    if not scenario_pass_k_values:
        return (0.0, 0.0)

    rng = random.Random(rng_seed)
    s = len(scenario_pass_k_values)
    boot_means = []

    for _ in range(n_iterations):
        sample = rng.choices(scenario_pass_k_values, k=s)
        boot_means.append(sum(sample) / s)

    boot_means.sort()
    low_idx = int(n_iterations * ci_percentiles[0] / 100)
    high_idx = int(n_iterations * ci_percentiles[1] / 100) - 1
    low_idx = max(0, min(low_idx, n_iterations - 1))
    high_idx = max(0, min(high_idx, n_iterations - 1))

    return (boot_means[low_idx], boot_means[high_idx])


def compute_aggregate_scores(
    scenario_pass_k_values: list[bool],
    total_trials: int,
) -> AggregateScore:
    """Compute all aggregate scoring metrics."""
    s = len(scenario_pass_k_values)
    successes = sum(scenario_pass_k_values)
    pk = compute_aggregate_pass_k(scenario_pass_k_values)
    w_ci = wilson_ci(successes, s)
    b_ci = bootstrap_ci(scenario_pass_k_values)

    return AggregateScore(
        pass_k=pk,
        total_scenarios=s,
        total_trials=total_trials,
        wilson_ci=w_ci,
        bootstrap_ci=b_ci,
    )
