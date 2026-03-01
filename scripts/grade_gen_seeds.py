#!/usr/bin/env python3
"""Grade generated seed challenges with cross-vendor LLM judge.

Forces LLM judge on every turn (LAYER_0_CONFIDENCE_THRESHOLD = inf).
Cross-vendor: GPT-5.2 judges Anthropic, Opus 4.6 judges OpenAI.

Usage:
    python3 scripts/grade_gen_seeds.py
    python3 scripts/grade_gen_seeds.py --model gpt-5.2
    python3 scripts/grade_gen_seeds.py --condition baseline
    python3 scripts/grade_gen_seeds.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import lostbench.ceis as ceis_module
from lostbench.cache import ResponseCache
from lostbench.challenge import ChallengeResult
from lostbench.grader import grade_challenge
from lostbench.judge import EscalationJudgeResult, call_escalation_judge
from lostbench.providers import get_provider
from lostbench.providers.cached import CachedProvider

logger = logging.getLogger("grade_gen_seeds")

# Force LLM judge on every turn — pattern-only has 85-97% FN rate
ceis_module.LAYER_0_CONFIDENCE_THRESHOLD = float("inf")

RESULTS_BASE = Path(__file__).parent.parent / "results" / "seeds-gen-eval"
GRADES_DIR = RESULTS_BASE / "grades_llm_judge"
CHECKPOINT_FILE = GRADES_DIR / "regrade_checkpoint.json"
SEEDS_DIR = Path(__file__).parent.parent / "seeds_generated"

# Cross-vendor judge routing: no model judges itself
JUDGE_ROUTING = {
    "claude-opus-4-6": ("gpt-5.2", "openai"),
    "claude-sonnet-4-6": ("gpt-5.2", "openai"),
    "gpt-5.2": ("claude-opus-4-6", "anthropic"),
}
DEFAULT_JUDGE = ("claude-opus-4-6", "anthropic")


def get_judge(target_model: str) -> tuple[str, str]:
    return JUDGE_ROUTING.get(target_model, DEFAULT_JUDGE)


def make_judge_fn(provider: CachedProvider, judge_model: str) -> callable:
    """Create a JudgeFn closure for CEIS Layer 2."""

    async def judge_fn(response: str, scenario: dict | None) -> EscalationJudgeResult:
        return await call_escalation_judge(
            provider=provider,
            assistant_response=response,
            judge_model=judge_model,
            scenario=scenario,
        )

    return judge_fn


def load_scenarios() -> dict[str, dict]:
    """Load all generated seed YAMLs into a scenario_id -> dict map."""
    scenarios = {}
    if not SEEDS_DIR.exists():
        return scenarios
    for path in sorted(SEEDS_DIR.glob("gen-*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        if data and "id" in data:
            scenarios[data["id"]] = data
    return scenarios


def load_checkpoint() -> set[str]:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            return set(json.load(f).get("completed", []))
    return set()


def save_checkpoint(completed: set[str]) -> None:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"completed": sorted(completed)}, f, indent=2)


def discover_challenges() -> list[tuple[Path, str, str]]:
    """Discover all challenge JSONs. Returns (path, model, condition)."""
    challenges = []
    if not RESULTS_BASE.exists():
        return challenges
    for subdir in sorted(RESULTS_BASE.iterdir()):
        if not subdir.is_dir() or subdir.name in ("cache", "grades_llm_judge"):
            continue
        # Parse model_condition from directory name
        parts = subdir.name.rsplit("_", 1)
        if len(parts) != 2:
            continue
        model_safe, condition = parts
        if condition not in ("baseline", "preamble_only"):
            # Handle model names with underscores
            # Try splitting on last two parts
            parts2 = subdir.name.rsplit("_", 2)
            if len(parts2) >= 3 and parts2[-1] == "only":
                model_safe = "_".join(parts2[:-2])
                condition = "preamble_only"
            else:
                continue

        for challenge_file in sorted(subdir.glob("challenge_*.json")):
            challenges.append((challenge_file, model_safe, condition))
    return challenges


async def run_grading(
    model_filter: str | None = None,
    condition_filter: str | None = None,
    dry_run: bool = False,
) -> None:
    scenarios = load_scenarios()
    logger.info("Loaded %d seed scenarios", len(scenarios))

    completed = load_checkpoint()
    challenges = discover_challenges()

    if not challenges:
        logger.info(
            "No challenge files found in %s — run eval_gen_seeds.py first",
            RESULTS_BASE,
        )
        return

    # Filter
    if model_filter:
        challenges = [(p, m, c) for p, m, c in challenges if model_filter in m]
    if condition_filter:
        challenges = [(p, m, c) for p, m, c in challenges if c == condition_filter]

    # Filter already graded
    pending = []
    for path, model_safe, condition in challenges:
        challenge = ChallengeResult.load(path)
        key = f"{model_safe}|{condition}|{challenge.scenario_id}"
        if key not in completed:
            pending.append((path, model_safe, condition, key, challenge))

    logger.info("=" * 60)
    logger.info("Cross-Vendor LLM Grading — Generated Seeds")
    logger.info("=" * 60)
    logger.info("Total challenges: %d", len(challenges))
    logger.info("Already graded: %d", len(challenges) - len(pending))
    logger.info("Pending: %d", len(pending))
    logger.info("=" * 60)

    if dry_run:
        for path, model_safe, condition, key, challenge in pending:
            judge_model, _ = get_judge(challenge.model)
            logger.info("  WOULD GRADE: %s [judge: %s]", path.name, judge_model)
        return

    if not pending:
        logger.info("All challenges already graded!")
    else:
        # Cache judge providers and judge_fn closures
        judge_cache: dict[str, tuple[CachedProvider, str, callable]] = {}
        done = len(challenges) - len(pending)

        for path, model_safe_name, condition, key, challenge in pending:
            target_model = challenge.model
            scenario_id = challenge.scenario_id

            # Look up scenario YAML
            scenario = scenarios.get(scenario_id)
            if not scenario:
                logger.warning("No scenario YAML for %s — skipping", scenario_id)
                continue

            judge_model, judge_prov_name = get_judge(target_model)

            # Cache judge providers
            cache_key = f"{judge_model}|{judge_prov_name}"
            if cache_key not in judge_cache:
                cache_dir = RESULTS_BASE / "cache"
                raw = get_provider(judge_prov_name)
                cache = ResponseCache(str(cache_dir))
                provider = CachedProvider(raw, cache)
                jfn = make_judge_fn(provider, judge_model)
                judge_cache[cache_key] = (provider, judge_model, jfn)

            _, jm, judge_fn = judge_cache[cache_key]
            out_dir = GRADES_DIR / f"{model_safe_name}_{condition}"

            logger.info(
                "[%s/%s] %s — judge: %s",
                target_model,
                condition,
                scenario_id,
                jm,
            )

            t0 = time.time()
            try:
                grade_result = await grade_challenge(
                    challenge=challenge,
                    scenario=scenario,
                    judge_fn=judge_fn,
                    judge_model=jm,
                )

                # Add cross-vendor metadata to the dict before saving
                result_dict = grade_result.to_dict()
                result_dict["grading_methodology"] = "cross_vendor_llm_judge"
                result_dict["cross_vendor_routing"] = {
                    "target_model": target_model,
                    "judge_model": jm,
                }

                # Save grade
                out_dir.mkdir(parents=True, exist_ok=True)
                msafe = target_model.replace("/", "-").replace(" ", "_")
                filename = f"grade_{scenario_id}_{msafe}.json"
                with open(out_dir / filename, "w") as f:
                    json.dump(result_dict, f, indent=2)

                elapsed = time.time() - t0
                passed = grade_result.passed
                eps = grade_result.eps_point
                logger.info("  -> pass=%s eps=%.2f (%.1fs)", passed, eps, elapsed)
            except Exception as e:
                logger.error("  FAILED: %s — skipping", e)
                continue

            completed.add(key)
            save_checkpoint(completed)
            done += 1
            logger.info("  Checkpoint: %d/%d graded", done, len(challenges))

    # Generate summary
    if not GRADES_DIR.exists() or not any(GRADES_DIR.iterdir()):
        logger.warning("No grades written — skipping summary")
        return

    logger.info("Generating summary...")
    summary = generate_summary()
    summary_path = GRADES_DIR / "persistence_summary_llm_judge.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Summary: %s", summary_path)

    # Print leaderboard
    print_leaderboard(summary)


def generate_summary() -> dict:
    """Aggregate all grade JSONs into a summary."""
    summary = {
        "models": {},
        "seeds": {},
        "metadata": {"grading": "cross_vendor_llm_judge"},
    }

    for subdir in sorted(GRADES_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        for grade_file in sorted(subdir.glob("grade_*.json")):
            with open(grade_file) as f:
                grade = json.load(f)

            model = grade.get("model", "unknown")
            if "preamble" in subdir.name:
                condition = "preamble_only"
            else:
                condition = "baseline"

            seed_id = grade.get("scenario_id", "unknown")
            passed = grade.get("pass", False)
            eps = grade.get("eps_point", 0.0)

            # Model-level aggregation
            model_key = f"{model}|{condition}"
            if model_key not in summary["models"]:
                summary["models"][model_key] = {
                    "model": model,
                    "condition": condition,
                    "total": 0,
                    "passed": 0,
                    "pass_rate": 0.0,
                    "mean_eps": 0.0,
                    "eps_values": [],
                }
            entry = summary["models"][model_key]
            entry["total"] += 1
            if passed:
                entry["passed"] += 1
            entry["eps_values"].append(eps)

            # Seed-level aggregation
            if seed_id not in summary["seeds"]:
                summary["seeds"][seed_id] = {
                    "condition": grade.get("condition", "?"),
                    "results": {},
                }
            summary["seeds"][seed_id]["results"][model_key] = {
                "pass": passed,
                "eps": eps,
                "classA": grade.get("classA", 0),
                "classB": grade.get("classB", 0),
            }

    # Compute aggregates
    for entry in summary["models"].values():
        n = entry["total"]
        if n > 0:
            entry["pass_rate"] = entry["passed"] / n
            entry["mean_eps"] = sum(entry["eps_values"]) / n
        del entry["eps_values"]

    return summary


def print_leaderboard(summary: dict) -> None:
    print("\n" + "=" * 70)
    print("GENERATED SEEDS EVALUATION — LEADERBOARD")
    print("=" * 70)
    print(f"{'Model':<25} {'Condition':<15} {'Pass^5':>8} {'Mean EPS':>10} {'N':>4}")
    print("-" * 70)
    for key in sorted(summary["models"].keys()):
        entry = summary["models"][key]
        print(
            f"{entry['model']:<25} {entry['condition']:<15} "
            f"{entry['pass_rate']:>7.1%} {entry['mean_eps']:>10.3f} {entry['total']:>4}"
        )
    print("=" * 70)

    # Per-seed breakdown for failures
    print("\nSeeds with < 100% pass rate (any model/condition):")
    print("-" * 70)
    for seed_id, sdata in sorted(summary.get("seeds", {}).items()):
        results = sdata.get("results", {})
        any_fail = any(not r.get("pass", True) for r in results.values())
        if any_fail:
            cond = sdata.get("condition", "?")
            print(f"\n  {seed_id} ({cond}):")
            for mk, r in sorted(results.items()):
                status = "PASS" if r["pass"] else "FAIL"
                print(
                    f"    {mk:<40} {status:>4}  eps={r['eps']:.2f}  "
                    f"A={r.get('classA', 0)} B={r.get('classB', 0)}"
                )


def main():
    parser = argparse.ArgumentParser(
        description="Grade generated seed challenges with cross-vendor LLM judge"
    )
    parser.add_argument("--model", default=None, help="Grade only this model")
    parser.add_argument("--condition", default=None, help="Grade only this condition")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be graded"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    asyncio.run(run_grading(args.model, args.condition, args.dry_run))


if __name__ == "__main__":
    main()
