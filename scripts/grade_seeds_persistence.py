#!/usr/bin/env python3
"""Grade seeds persistence challenges and compute leaderboard numbers.

Reads challenge JSONs, grades via pattern-only CEIS, computes pass^5 per
model/condition, and outputs the numbers needed for the persistence table.

Usage:
    python3 scripts/grade_seeds_persistence.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml

from lostbench.challenge import ChallengeResult
from lostbench.grader import grade_challenge

logger = logging.getLogger("grade_seeds")

RESULTS_DIR = Path(__file__).parent.parent / "results" / "seeds-persistence"
SEEDS_DIR = Path(__file__).parent.parent / "seeds_mined"


def load_scenarios() -> dict[str, dict]:
    """Load mined seed scenarios as lookup dict."""
    scenarios = {}
    for path in sorted(SEEDS_DIR.glob("*.yaml")):
        with open(path) as f:
            s = yaml.safe_load(f)
        scenarios[s["id"]] = s
    return scenarios


def load_challenges(subdir: str) -> list[ChallengeResult]:
    """Load all challenge results from a subdirectory."""
    d = RESULTS_DIR / subdir
    results = []
    for path in sorted(d.glob("challenge_*.json")):
        results.append(ChallengeResult.load(path))
    return results


async def grade_all():
    """Grade all challenges and compute persistence metrics."""
    scenarios = load_scenarios()
    logger.info("Loaded %d seed scenarios", len(scenarios))

    # Discover all model/condition directories
    subdirs = [
        d.name
        for d in sorted(RESULTS_DIR.iterdir())
        if d.is_dir() and d.name != "cache"
    ]

    # Grade each challenge
    # Structure: results[model][condition][seed_id] = {passed, pass_rate, responses}
    results: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))

    for subdir in subdirs:
        # Parse model and condition from dirname: "model_condition"
        parts = subdir.rsplit("_", 1)
        if len(parts) == 2 and parts[1] in ("baseline", "only"):
            # Handle "preamble_only" -> need to split differently
            pass

        # More robust: find the condition suffix
        if subdir.endswith("_baseline"):
            model = subdir[: -len("_baseline")]
            condition = "baseline"
        elif subdir.endswith("_preamble_only"):
            model = subdir[: -len("_preamble_only")]
            condition = "preamble_only"
        else:
            logger.warning("Skipping unknown dir: %s", subdir)
            continue

        challenges = load_challenges(subdir)
        logger.info("Grading %s/%s: %d challenges", model, condition, len(challenges))

        for challenge in challenges:
            sid = challenge.scenario_id
            scenario = scenarios.get(sid)
            if not scenario:
                logger.warning("  No scenario for %s — skipping", sid)
                continue

            grade = await grade_challenge(
                challenge=challenge,
                scenario=scenario,
                judge_fn=None,  # Pattern-only
                judge_model="pattern-only",
            )

            # Per-trial pass assessment
            trial_results = []
            for transcript in challenge.transcripts:
                # A trial passes if no response triggered a failure pattern
                # Grade gives us aggregate — we need per-trial info
                # For now, use the grade's pass_rate
                trial_results.append(transcript)

            results[model][condition][sid] = {
                "passed": grade.passed,
                "pass_rate": grade.pass_rate,
                "failure_mode": grade.failure_mode,
                "classA": grade.classA,
                "severity": grade.severity,
            }

    return dict(results)


def compute_persistence_metrics(results: dict) -> None:
    """Compute and print persistence table numbers."""
    print("\n" + "=" * 80)
    print("SEEDS PERSISTENCE RESULTS")
    print("=" * 80)

    for model in sorted(results.keys()):
        conditions = results[model]
        print(f"\n--- {model} ---")

        for condition in ["baseline", "preamble_only"]:
            if condition not in conditions:
                continue

            grades = conditions[condition]
            n_seeds = len(grades)
            n_passed = sum(1 for g in grades.values() if g["passed"])
            n_passed / n_seeds if n_seeds else 0

            # pass^5: for each seed, pass_rate^5
            # But we actually need per-trial data. Since grade gives us
            # pass_rate (fraction of trials that pass), pass^5 = product
            # of per-trial pass probability across 5 trials.
            # For the leaderboard, pass^5 = fraction of seeds where ALL 5 trials pass.
            # grade.passed is True only if pass_rate == 1.0 (all trials pass)

            pass5 = n_passed / n_seeds if n_seeds else 0

            # Per-trial pass rate (average across seeds)
            avg_per_trial = (
                sum(g["pass_rate"] for g in grades.values()) / n_seeds if n_seeds else 0
            )

            # Total classA
            total_classA = sum(g["classA"] for g in grades.values())

            # Unsolved seeds (0% pass rate)
            unsolved = [sid for sid, g in grades.items() if g["pass_rate"] == 0.0]

            print(f"  {condition}:")
            print(f"    Seeds: {n_seeds}")
            print(f"    Per-trial pass rate: {avg_per_trial:.3f} ({avg_per_trial:.1%})")
            print(f"    Pass^5 (all trials): {pass5:.3f} ({pass5:.1%})")
            print(f"    Total Class A: {total_classA}")
            print(
                f"    Unsolved seeds ({len(unsolved)}): {', '.join(sorted(unsolved))}"
            )

            # Per-seed breakdown
            print("    Per-seed:")
            for sid in sorted(grades.keys()):
                g = grades[sid]
                status = "PASS" if g["passed"] else "FAIL"
                print(
                    f"      {sid}: {status} (rate={g['pass_rate']:.1%}, "
                    f"mode={g['failure_mode']}, classA={g['classA']})"
                )

    # Print leaderboard-ready table
    print("\n" + "=" * 80)
    print("LEADERBOARD TABLE (copy to generate_leaderboard.py)")
    print("=" * 80)
    print(f"{'Model':<45} {'Base Pass^5':>12} {'Mit Pass^5':>12} {'Unsolved':>10}")
    print("-" * 80)

    for model in sorted(results.keys()):
        conditions = results[model]
        base = conditions.get("baseline", {})
        preamble = conditions.get("preamble_only", {})

        n_base = len(base)
        n_prem = len(preamble)

        base_pass5 = (
            sum(1 for g in base.values() if g["passed"]) / n_base if n_base else 0
        )
        prem_pass5 = (
            sum(1 for g in preamble.values() if g["passed"]) / n_prem if n_prem else 0
        )

        # Unsolved = seeds with 0% in BOTH conditions
        all_seeds = set(base.keys()) | set(preamble.keys())
        unsolved = sum(
            1
            for sid in all_seeds
            if base.get(sid, {}).get("pass_rate", 0) == 0
            and preamble.get(sid, {}).get("pass_rate", 0) == 0
        )

        print(f"{model:<45} {base_pass5:>11.1%} {prem_pass5:>11.1%} {unsolved:>10}")

    # Save raw results as JSON
    output = RESULTS_DIR / "persistence_summary.json"
    with open(output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw results saved: {output}")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    results = asyncio.run(grade_all())
    compute_persistence_metrics(results)


if __name__ == "__main__":
    main()
