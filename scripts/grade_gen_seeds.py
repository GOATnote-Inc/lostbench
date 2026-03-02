#!/usr/bin/env python3
"""Grade generated seed challenges with cross-vendor LLM judge.

Forces LLM judge on every turn (LAYER_0_CONFIDENCE_THRESHOLD = inf).
Cross-vendor: GPT-5.2 judges Anthropic, Opus 4.6 judges OpenAI.

Usage:
    python3 scripts/grade_gen_seeds.py
    python3 scripts/grade_gen_seeds.py --model gpt-5.2
    python3 scripts/grade_gen_seeds.py --condition baseline
    python3 scripts/grade_gen_seeds.py --dry-run
    python3 scripts/grade_gen_seeds.py --seeds-dir seeds_generated/eval_batch --results-dir results/seeds-cycle-eval
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

DEFAULT_RESULTS_BASE = Path(__file__).parent.parent / "results" / "seeds-gen-eval"
DEFAULT_SEEDS_DIR = Path(__file__).parent.parent / "seeds_generated"

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


def load_scenarios(seeds_dir: Path) -> dict[str, dict]:
    """Load all generated seed YAMLs into a scenario_id -> dict map."""
    scenarios = {}
    if not seeds_dir.exists():
        return scenarios
    for path in sorted(seeds_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        with open(path) as f:
            data = yaml.safe_load(f)
        if data and "id" in data:
            scenarios[data["id"]] = data
    return scenarios


def load_checkpoint(checkpoint_file: Path) -> set[str]:
    if checkpoint_file.exists():
        with open(checkpoint_file) as f:
            return set(json.load(f).get("completed", []))
    return set()


def save_checkpoint(completed: set[str], checkpoint_file: Path) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_file, "w") as f:
        json.dump({"completed": sorted(completed)}, f, indent=2)


def discover_challenges(results_base: Path) -> list[tuple[Path, str, str]]:
    """Discover all challenge JSONs. Returns (path, model, condition)."""
    challenges = []
    if not results_base.exists():
        return challenges
    for subdir in sorted(results_base.iterdir()):
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
    results_base: Path = DEFAULT_RESULTS_BASE,
    seeds_dir: Path = DEFAULT_SEEDS_DIR,
) -> None:
    grades_dir = results_base / "grades_llm_judge"
    checkpoint_file = grades_dir / "regrade_checkpoint.json"

    scenarios = load_scenarios(seeds_dir)
    logger.info("Loaded %d seed scenarios", len(scenarios))

    completed = load_checkpoint(checkpoint_file)
    challenges = discover_challenges(results_base)

    if not challenges:
        logger.info(
            "No challenge files found in %s — run eval_gen_seeds.py first",
            results_base,
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
                cache_dir = results_base / "cache"
                raw = get_provider(judge_prov_name)
                cache = ResponseCache(str(cache_dir))
                provider = CachedProvider(raw, cache)
                jfn = make_judge_fn(provider, judge_model)
                judge_cache[cache_key] = (provider, judge_model, jfn)

            _, jm, judge_fn = judge_cache[cache_key]
            out_dir = grades_dir / f"{model_safe_name}_{condition}"

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
            save_checkpoint(completed, checkpoint_file)
            done += 1
            logger.info("  Checkpoint: %d/%d graded", done, len(challenges))

    # Generate summary
    if not grades_dir.exists() or not any(grades_dir.iterdir()):
        logger.warning("No grades written — skipping summary")
        return

    logger.info("Generating summary...")
    summary = generate_summary(grades_dir)
    summary_path = grades_dir / "persistence_summary_llm_judge.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Summary: %s", summary_path)

    # Print leaderboard
    print_leaderboard(summary)


def generate_summary(grades_dir: Path | None = None) -> dict:
    """Aggregate all grade JSONs into a summary."""
    if grades_dir is None:
        grades_dir = DEFAULT_RESULTS_BASE / "grades_llm_judge"
    summary = {
        "models": {},
        "seeds": {},
        "categories": {},
        "metadata": {"grading": "cross_vendor_llm_judge"},
    }

    for subdir in sorted(grades_dir.iterdir()):
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
            trial_pass_rate = grade.get("pass_rate", 1.0 if passed else 0.0)
            n_trials = grade.get("reproduction", {}).get("trial_count", 5) or 5
            condition_name = grade.get("condition", "unknown")

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
                    "trial_pass_rates": [],
                    "n_trials": n_trials,
                }
            entry = summary["models"][model_key]
            entry["total"] += 1
            if passed:
                entry["passed"] += 1
            entry["eps_values"].append(eps)
            entry["trial_pass_rates"].append(trial_pass_rate)

            # Seed-level aggregation
            if seed_id not in summary["seeds"]:
                summary["seeds"][seed_id] = {
                    "condition": condition_name,
                    "results": {},
                }
            summary["seeds"][seed_id]["results"][model_key] = {
                "pass": passed,
                "eps": eps,
                "trial_pass_rate": trial_pass_rate,
                "classA": grade.get("classA", 0),
                "classB": grade.get("classB", 0),
            }

            # Category-level aggregation
            cat_key = f"{condition_name}|{model_key}"
            if cat_key not in summary["categories"]:
                summary["categories"][cat_key] = {
                    "condition_name": condition_name,
                    "model": model,
                    "eval_condition": condition,
                    "total": 0,
                    "passed": 0,
                    "trial_pass_rates": [],
                }
            cat = summary["categories"][cat_key]
            cat["total"] += 1
            if passed:
                cat["passed"] += 1
            cat["trial_pass_rates"].append(trial_pass_rate)

    # Compute aggregates
    for entry in summary["models"].values():
        n = entry["total"]
        k = entry["n_trials"]
        if n > 0:
            entry["pass_rate"] = entry["passed"] / n
            entry["mean_eps"] = sum(entry["eps_values"]) / n
            rates = entry["trial_pass_rates"]
            mean_rate = sum(rates) / len(rates)
            entry["mean_trial_pass_rate"] = round(mean_rate, 4)
            # pass@k: mean P(at least 1 pass in k trials)
            entry["pass_at_k"] = round(
                sum(1 - (1 - r) ** k for r in rates) / len(rates), 4
            )
            # pass^k: mean P(all k trials pass)
            entry["pass_pow_k"] = round(sum(r**k for r in rates) / len(rates), 4)
            # Failure distribution
            entry["always_fail"] = sum(1 for r in rates if r == 0.0)
            entry["always_pass"] = sum(1 for r in rates if r == 1.0)
            entry["intermittent"] = n - entry["always_fail"] - entry["always_pass"]
        del entry["eps_values"]
        del entry["trial_pass_rates"]

    # Category aggregates
    for cat in summary["categories"].values():
        n = cat["total"]
        if n > 0:
            cat["pass_rate"] = round(cat["passed"] / n, 4)
            rates = cat["trial_pass_rates"]
            cat["mean_trial_pass_rate"] = round(sum(rates) / len(rates), 4)
        del cat["trial_pass_rates"]

    return summary


def print_leaderboard(summary: dict) -> None:
    print("\n" + "=" * 90)
    print("GENERATED SEEDS EVALUATION — LEADERBOARD")
    print("=" * 90)
    print(
        f"{'Model':<25} {'Condition':<15} {'Pass%':>7} {'pass@k':>8} "
        f"{'pass^k':>8} {'MeanEPS':>9} {'Alw.F':>6} {'Inter':>6} {'Alw.P':>6} {'N':>4}"
    )
    print("-" * 90)
    for key in sorted(summary["models"].keys()):
        e = summary["models"][key]
        print(
            f"{e['model']:<25} {e['condition']:<15} "
            f"{e['pass_rate']:>6.1%} {e.get('pass_at_k', 0):>7.1%} "
            f"{e.get('pass_pow_k', 0):>7.1%} {e['mean_eps']:>9.3f} "
            f"{e.get('always_fail', 0):>6} {e.get('intermittent', 0):>6} "
            f"{e.get('always_pass', 0):>6} {e['total']:>4}"
        )
    print("=" * 90)

    # Category breakdown (top failures)
    cats = summary.get("categories", {})
    if cats:
        print("\nPer-condition failures (conditions with <100% pass, any cell):")
        print("-" * 70)
        # Group by condition_name, show worst cell
        from collections import defaultdict

        by_cond: dict[str, list] = defaultdict(list)
        for cat in cats.values():
            by_cond[cat["condition_name"]].append(cat)
        for cond_name in sorted(by_cond.keys()):
            entries = by_cond[cond_name]
            worst = min(entries, key=lambda c: c["pass_rate"])
            if worst["pass_rate"] < 1.0:
                print(
                    f"  {cond_name:<40} worst={worst['pass_rate']:.0%} "
                    f"({worst['model']}/{worst['eval_condition']})"
                )

    # Per-seed breakdown for failures
    print("\nSeeds with < 100% pass rate (any model/condition):")
    print("-" * 90)
    for seed_id, sdata in sorted(summary.get("seeds", {}).items()):
        results = sdata.get("results", {})
        any_fail = any(not r.get("pass", True) for r in results.values())
        if any_fail:
            cond = sdata.get("condition", "?")
            print(f"\n  {seed_id} ({cond}):")
            for mk, r in sorted(results.items()):
                status = "PASS" if r["pass"] else "FAIL"
                tpr = r.get("trial_pass_rate", "?")
                tpr_str = f"{tpr:.0%}" if isinstance(tpr, float) else tpr
                print(
                    f"    {mk:<40} {status:>4}  eps={r['eps']:.2f}  "
                    f"tpr={tpr_str:>4}  A={r.get('classA', 0)} B={r.get('classB', 0)}"
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
    parser.add_argument(
        "--seeds-dir",
        type=Path,
        default=DEFAULT_SEEDS_DIR,
        help=f"Directory containing seed YAMLs (default: {DEFAULT_SEEDS_DIR})",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_BASE,
        help=f"Results directory with challenge JSONs (default: {DEFAULT_RESULTS_BASE})",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    asyncio.run(
        run_grading(
            args.model,
            args.condition,
            args.dry_run,
            results_base=args.results_dir,
            seeds_dir=args.seeds_dir,
        )
    )


if __name__ == "__main__":
    main()
