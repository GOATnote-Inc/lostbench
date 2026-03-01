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

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import lostbench.ceis as ceis_module
from lostbench.cache import ResponseCache
from lostbench.grader import grade_challenge
from lostbench.providers import get_provider
from lostbench.providers.cached import CachedProvider

logger = logging.getLogger("grade_gen_seeds")

# Force LLM judge on every turn — pattern-only has 85-97% FN rate
ceis_module.LAYER_0_CONFIDENCE_THRESHOLD = float("inf")

RESULTS_BASE = Path(__file__).parent.parent / "results" / "seeds-gen-eval"
GRADES_DIR = RESULTS_BASE / "grades_llm_judge"
CHECKPOINT_FILE = GRADES_DIR / "regrade_checkpoint.json"

# Cross-vendor judge routing: no model judges itself
JUDGE_ROUTING = {
    "claude-opus-4-6": ("gpt-5.2", "openai"),
    "claude-sonnet-4-6": ("gpt-5.2", "openai"),
    "gpt-5.2": ("claude-opus-4-6", "anthropic"),
}
DEFAULT_JUDGE = ("claude-opus-4-6", "anthropic")


def get_judge(target_model: str) -> tuple[str, str]:
    return JUDGE_ROUTING.get(target_model, DEFAULT_JUDGE)


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


async def grade_one(
    challenge_path: Path,
    judge_provider: CachedProvider,
    judge_model: str,
    target_model: str,
    output_dir: Path,
) -> dict:
    """Grade a single challenge JSON."""
    with open(challenge_path) as f:
        challenge_data = json.load(f)

    result = await grade_challenge(
        challenge_data=challenge_data,
        judge_provider=judge_provider,
        judge_model=judge_model,
    )

    # Add cross-vendor metadata
    result["grading_methodology"] = "cross_vendor_llm_judge"
    result["cross_vendor_routing"] = {
        "target_model": target_model,
        "judge_model": judge_model,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_id = challenge_data.get("scenario_id", "unknown")
    msafe = target_model.replace("/", "-").replace(" ", "_")
    filename = f"grade_{scenario_id}_{msafe}.json"
    with open(output_dir / filename, "w") as f:
        json.dump(result, f, indent=2)

    return result


async def run_grading(
    model_filter: str | None = None,
    condition_filter: str | None = None,
    dry_run: bool = False,
) -> None:
    completed = load_checkpoint()
    challenges = discover_challenges()

    if not challenges:
        logger.info(
            "No challenge files found in %s — run eval_gen_seeds.py first", RESULTS_BASE
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
        key = f"{model_safe}|{condition}|{path.name}"
        if key not in completed:
            pending.append((path, model_safe, condition, key))

    logger.info("=" * 60)
    logger.info("Cross-Vendor LLM Grading — Generated Seeds")
    logger.info("=" * 60)
    logger.info("Total challenges: %d", len(challenges))
    logger.info("Already graded: %d", len(challenges) - len(pending))
    logger.info("Pending: %d", len(pending))
    logger.info("=" * 60)

    if dry_run:
        for path, model_safe, condition, key in pending:
            target = path.parent.name.rsplit("_", 1)[0]
            judge_model, judge_provider = get_judge(
                target.replace("-", ".").replace("_", "-")
            )
            logger.info("  WOULD GRADE: %s [judge: %s]", path.name, judge_model)
        return

    if not pending:
        logger.info("All challenges already graded!")
    else:
        # Group by target model for provider reuse
        judge_cache = {}
        done = len(challenges) - len(pending)

        for path, model_safe_name, condition, key in pending:
            # Resolve actual model name from challenge JSON
            with open(path) as f:
                cdata = json.load(f)
            target_model = cdata.get("model", model_safe_name)

            judge_model, judge_prov_name = get_judge(target_model)

            # Cache judge providers
            cache_key = f"{judge_model}|{judge_prov_name}"
            if cache_key not in judge_cache:
                cache_dir = RESULTS_BASE / "cache"
                raw = get_provider(judge_prov_name)
                cache = ResponseCache(str(cache_dir))
                judge_cache[cache_key] = CachedProvider(raw, cache)

            provider = judge_cache[cache_key]
            out_dir = GRADES_DIR / f"{model_safe_name}_{condition}"

            scenario_id = cdata.get("scenario_id", "?")
            logger.info(
                "[%s/%s] %s — judge: %s",
                target_model,
                condition,
                scenario_id,
                judge_model,
            )

            t0 = time.time()
            try:
                result = await grade_one(
                    path, provider, judge_model, target_model, out_dir
                )
                elapsed = time.time() - t0
                passed = result.get("pass", "?")
                eps = result.get("eps_point", "?")
                logger.info("  -> pass=%s eps=%.2f (%.1fs)", passed, eps, elapsed)
            except Exception as e:
                logger.error("  FAILED: %s — skipping", e)
                continue

            completed.add(key)
            save_checkpoint(completed)
            done += 1
            logger.info("  Checkpoint: %d/%d graded", done, len(challenges))

    # Generate summary
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
            condition = subdir.name.split("_")[-1]
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
