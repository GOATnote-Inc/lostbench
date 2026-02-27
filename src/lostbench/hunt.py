"""Hunt — Adaptive discovery orchestrator.

Four hunting strategies for systematic vulnerability discovery:
1. adversarial_escalation — Find the ceiling (make passing scenarios harder)
2. boundary_probing — Find the decision boundary (mixed-result scenarios)
3. coverage_gaps — Fill blind spots in attack taxonomy
4. regression_testing — Verify fixes after model updates

Iterates: select scenarios -> challenge -> grade -> update risk picture -> repeat.

Usage:
    from lostbench.hunt import run_hunt, HuntConfig
    results = await run_hunt(config)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from lostbench.challenge import ChallengeResult, run_challenge
from lostbench.grader import GradeResult, grade_challenge
from lostbench.providers.base import Provider
from lostbench.ceis import JudgeFn

logger = logging.getLogger(__name__)

HuntStrategy = Literal[
    "adversarial_escalation",
    "boundary_probing",
    "coverage_gaps",
    "regression_testing",
]

VALID_STRATEGIES: set[str] = {
    "adversarial_escalation",
    "boundary_probing",
    "coverage_gaps",
    "regression_testing",
}


@dataclass
class HuntConfig:
    """Configuration for a hunt campaign."""

    model: str
    provider_name: str
    strategy: HuntStrategy
    scenarios: list[dict]
    n_trials: int = 5
    rounds: int = 3
    temperature: float = 0.0
    seed: int = 42
    system_prompt: str | None = None
    judge_model: str = ""
    output_dir: str = "."
    # Strategy-specific
    target_per_class: int = 5  # for coverage_gaps
    seed_scenario_id: str | None = None  # for boundary_probing
    n_variants: int = 3  # for boundary_probing


@dataclass
class HuntRound:
    """Results from a single hunt round."""

    round_num: int
    scenarios_tested: list[str]
    challenges: list[ChallengeResult]
    grades: list[GradeResult]
    new_failures: list[str]
    timestamp: str = ""


@dataclass
class HuntResult:
    """Complete result of a hunt campaign."""

    strategy: str
    model: str
    rounds_completed: int
    total_scenarios: int
    total_failures: int
    rounds: list[HuntRound] = field(default_factory=list)
    coverage: dict[str, int] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "model": self.model,
            "rounds_completed": self.rounds_completed,
            "total_scenarios": self.total_scenarios,
            "total_failures": self.total_failures,
            "rounds": [
                {
                    "round_num": r.round_num,
                    "scenarios_tested": r.scenarios_tested,
                    "new_failures": r.new_failures,
                    "n_challenges": len(r.challenges),
                    "n_grades": len(r.grades),
                }
                for r in self.rounds
            ],
            "coverage": self.coverage,
            "timestamp": self.timestamp,
        }


def _select_scenarios_adversarial_escalation(
    scenarios: list[dict],
    prior_grades: list[GradeResult],
) -> list[dict]:
    """Select scenarios that currently pass — they need harder variants."""
    passing_ids = {g.scenario_id for g in prior_grades if g.passed}
    if not passing_ids:
        # If nothing passes yet, return all scenarios
        return scenarios
    return [s for s in scenarios if s["id"] in passing_ids]


def _select_scenarios_boundary_probing(
    scenarios: list[dict],
    prior_grades: list[GradeResult],
    seed_id: str | None = None,
) -> list[dict]:
    """Select mixed-result scenarios (partial pass) — most informative region."""
    if seed_id:
        return [s for s in scenarios if s["id"] == seed_id]

    # Find scenarios with 20-80% pass rate (mixed results)
    mixed_ids = {g.scenario_id for g in prior_grades if 0.2 <= g.pass_rate <= 0.8}
    if not mixed_ids:
        # Fall back to all non-perfect scenarios
        mixed_ids = {g.scenario_id for g in prior_grades if g.pass_rate < 1.0}
    return [s for s in scenarios if s["id"] in mixed_ids]


def _select_scenarios_coverage_gaps(
    scenarios: list[dict],
    prior_grades: list[GradeResult],
    target_per_class: int = 5,
) -> list[dict]:
    """Identify attack families with < target_per_class scenarios."""
    # Count scenarios per attack family / corpus
    family_counts: dict[str, int] = {}
    for s in scenarios:
        family = s.get("attack_family", s.get("corpus", "unknown"))
        family_counts[family] = family_counts.get(family, 0) + 1

    # Find under-represented families
    gap_families = {f for f, c in family_counts.items() if c < target_per_class}

    if not gap_families:
        return scenarios[:target_per_class]

    return [
        s
        for s in scenarios
        if s.get("attack_family", s.get("corpus", "unknown")) in gap_families
    ]


def _select_scenarios_regression(
    scenarios: list[dict],
    prior_grades: list[GradeResult],
) -> list[dict]:
    """Select all scenarios for regression testing."""
    # Test everything — regression is about breadth
    return scenarios


def select_scenarios(
    strategy: HuntStrategy,
    scenarios: list[dict],
    prior_grades: list[GradeResult],
    config: HuntConfig,
) -> list[dict]:
    """Select scenarios based on hunting strategy."""
    if strategy == "adversarial_escalation":
        return _select_scenarios_adversarial_escalation(scenarios, prior_grades)
    elif strategy == "boundary_probing":
        return _select_scenarios_boundary_probing(
            scenarios, prior_grades, config.seed_scenario_id
        )
    elif strategy == "coverage_gaps":
        return _select_scenarios_coverage_gaps(
            scenarios, prior_grades, config.target_per_class
        )
    elif strategy == "regression_testing":
        return _select_scenarios_regression(scenarios, prior_grades)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


async def run_hunt_round(
    round_num: int,
    scenarios: list[dict],
    provider: Provider,
    config: HuntConfig,
    judge_fn: JudgeFn | None = None,
    scenario_lookup: dict[str, dict] | None = None,
) -> HuntRound:
    """Execute a single hunt round: challenge + grade selected scenarios."""
    logger.info(
        "Hunt round %d: %d scenarios, strategy=%s",
        round_num,
        len(scenarios),
        config.strategy,
    )

    challenges: list[ChallengeResult] = []
    grades: list[GradeResult] = []
    new_failures: list[str] = []

    for scenario in scenarios:
        # Challenge
        challenge = await run_challenge(
            scenario=scenario,
            provider=provider,
            model=config.model,
            n_trials=config.n_trials,
            temperature=config.temperature,
            seed=config.seed,
            system_prompt=config.system_prompt,
        )
        challenges.append(challenge)

        # Grade
        grade = await grade_challenge(
            challenge=challenge,
            scenario=scenario,
            judge_fn=judge_fn,
            judge_model=config.judge_model,
        )
        grades.append(grade)

        if not grade.passed:
            new_failures.append(grade.scenario_id)
            logger.info(
                "  FAIL: %s (%s) — %s at turn %d",
                grade.scenario_id,
                grade.condition,
                grade.failure_mode,
                grade.failure_turn,
            )

    return HuntRound(
        round_num=round_num,
        scenarios_tested=[s["id"] for s in scenarios],
        challenges=challenges,
        grades=grades,
        new_failures=new_failures,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


async def run_hunt(
    config: HuntConfig,
    provider: Provider,
    judge_fn: JudgeFn | None = None,
) -> HuntResult:
    """Run a full hunt campaign across multiple rounds.

    Each round:
    1. Select scenarios based on strategy and prior results
    2. Challenge (run model against scenarios)
    3. Grade (classify failures)
    4. Update risk picture

    Args:
        config: Hunt campaign configuration.
        provider: Model provider for API calls.
        judge_fn: Optional LLM judge callback.

    Returns:
        HuntResult with all rounds and aggregate metrics.
    """
    if config.strategy not in VALID_STRATEGIES:
        raise ValueError(
            f"Unknown strategy: {config.strategy}. Valid: {sorted(VALID_STRATEGIES)}"
        )

    scenario_lookup = {s["id"]: s for s in config.scenarios}
    all_grades: list[GradeResult] = []
    rounds: list[HuntRound] = []

    for round_num in range(1, config.rounds + 1):
        # Select scenarios for this round
        selected = select_scenarios(
            config.strategy, config.scenarios, all_grades, config
        )

        if not selected:
            logger.info("Round %d: no scenarios selected, stopping", round_num)
            break

        # Prioritize by severity x exploitability
        selected.sort(
            key=lambda s: (
                -s.get("ceis", {}).get("severity_weight", 0.7),
                s.get("id", ""),
            )
        )

        # Run round
        hunt_round = await run_hunt_round(
            round_num=round_num,
            scenarios=selected,
            provider=provider,
            config=config,
            judge_fn=judge_fn,
            scenario_lookup=scenario_lookup,
        )
        rounds.append(hunt_round)
        all_grades.extend(hunt_round.grades)

        logger.info(
            "Round %d complete: %d tested, %d failures",
            round_num,
            len(selected),
            len(hunt_round.new_failures),
        )

    # Compute coverage stats
    coverage: dict[str, int] = {}
    for g in all_grades:
        family = g.condition  # Use condition as proxy for family
        coverage[family] = coverage.get(family, 0) + 1

    total_failures = sum(1 for g in all_grades if not g.passed)

    return HuntResult(
        strategy=config.strategy,
        model=config.model,
        rounds_completed=len(rounds),
        total_scenarios=len(all_grades),
        total_failures=total_failures,
        rounds=rounds,
        coverage=coverage,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
