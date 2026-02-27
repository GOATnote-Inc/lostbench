#!/usr/bin/env python3
"""Regrade seeds persistence challenges with cross-vendor LLM judge on EVERY turn.

Pattern-only grading (Layer 0) has 85-97% false negative rate — it passes too
much. This script forces the LLM judge on every single response (sets Layer 0
confidence threshold to infinity so no response escapes LLM evaluation).

Cross-vendor judge routing (no model family judges itself):
  - Grok (xAI)           → judged by claude-opus-4-6 (Anthropic)
  - Gemini (Google)       → judged by claude-opus-4-6 (Anthropic)
  - Claude Opus 4.6       → judged by gpt-5.2 (OpenAI)
  - GPT-5.2 (OpenAI)     → judged by claude-opus-4-6 (Anthropic)

Each grade file preserves the full judge provenance chain: Layer 0 pattern
result, Layer 2 LLM judge raw output, confidence, evidence snippet, failure
class, challenge input hash, judge model ID, rubric version.

Usage:
    python3 scripts/regrade_seeds_llm_judge.py
    python3 scripts/regrade_seeds_llm_judge.py --model grok-4-1-fast-reasoning-latest
    python3 scripts/regrade_seeds_llm_judge.py --dry-run  # show what would be graded
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml

import lostbench.ceis as ceis_module
from lostbench.cache import ResponseCache
from lostbench.challenge import ChallengeResult
from lostbench.grader import GradeResult, grade_challenge
from lostbench.judge import EscalationJudgeResult, call_escalation_judge
from lostbench.providers import get_provider
from lostbench.providers.cached import CachedProvider

# Force LLM judge on EVERY response — do not trust Layer 0 pattern grading.
# Pattern-only has 85-97% FN rate (proven on Opus 4.6 baseline: pattern said 4%,
# LLM judge said 54%). Setting threshold to infinity ensures judge_fn is always called.
ceis_module.LAYER_0_CONFIDENCE_THRESHOLD = float("inf")

logger = logging.getLogger("regrade_seeds")

# --- Cross-Vendor Judge Routing ---
# Rule: no model family judges itself. Each target model maps to (judge_model, provider).

JUDGE_ROUTING = {
    # xAI → Anthropic judge
    "grok-4-1-fast-reasoning-latest": ("claude-opus-4-6", "anthropic"),
    # Google → Anthropic judge
    "gemini-3.1-pro-preview": ("claude-opus-4-6", "anthropic"),
    # Anthropic → OpenAI judge
    "claude-opus-4-6": ("gpt-5.2", "openai"),
    "claude-sonnet-4-6": ("gpt-5.2", "openai"),
    "claude-sonnet-4-5-20250929": ("gpt-5.2", "openai"),
    # OpenAI → Anthropic judge
    "gpt-5.2": ("claude-opus-4-6", "anthropic"),
}

# Fallback: unknown models get judged by Anthropic
DEFAULT_JUDGE = ("claude-opus-4-6", "anthropic")

RESULTS_DIR = Path(__file__).parent.parent / "results" / "seeds-persistence"
SEEDS_DIR = Path(__file__).parent.parent / "seeds_mined"
GRADES_DIR = RESULTS_DIR / "grades_llm_judge"
CHECKPOINT_FILE = GRADES_DIR / "regrade_checkpoint.json"


def get_judge_for_model(target_model: str) -> tuple[str, str]:
    """Return (judge_model, judge_provider) for a target model."""
    return JUDGE_ROUTING.get(target_model, DEFAULT_JUDGE)


def load_scenarios() -> dict[str, dict]:
    """Load mined seed scenarios as lookup dict."""
    scenarios = {}
    for path in sorted(SEEDS_DIR.glob("*.yaml")):
        with open(path) as f:
            s = yaml.safe_load(f)
        scenarios[s["id"]] = s
    return scenarios


def discover_challenges() -> list[tuple[str, str, Path]]:
    """Find all challenge files. Returns [(model, condition, path)]."""
    challenges = []
    for subdir in sorted(RESULTS_DIR.iterdir()):
        if not subdir.is_dir() or subdir.name in ("cache", "grades_llm_judge"):
            continue

        # Parse model and condition from dirname
        if subdir.name.endswith("_baseline"):
            model = subdir.name[: -len("_baseline")]
            condition = "baseline"
        elif subdir.name.endswith("_preamble_only"):
            model = subdir.name[: -len("_preamble_only")]
            condition = "preamble_only"
        else:
            continue

        for path in sorted(subdir.glob("challenge_*.json")):
            challenges.append((model, condition, path))

    return challenges


def load_checkpoint() -> set[str]:
    """Load set of completed grade keys "model|condition|seed_id"."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        return set(data.get("completed", []))
    return set()


def save_checkpoint(completed: set[str]) -> None:
    """Save checkpoint state."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"completed": sorted(completed)}, f, indent=2)


def make_judge_fn(provider: CachedProvider, judge_model: str):
    """Create a JudgeFn closure for CEIS Layer 2."""

    async def judge_fn(response: str, scenario: dict | None) -> EscalationJudgeResult:
        return await call_escalation_judge(
            provider=provider,
            assistant_response=response,
            judge_model=judge_model,
            scenario=scenario,
        )

    return judge_fn


# Cache judge providers to avoid creating multiple instances per family
_judge_cache: dict[str, tuple[CachedProvider, str]] = {}


def get_judge_provider_and_fn(target_model: str, cache_dir: Path) -> tuple[str, object]:
    """Get or create a cached judge provider+fn for a target model."""
    judge_model, judge_provider_name = get_judge_for_model(target_model)

    cache_key = f"{judge_provider_name}:{judge_model}"
    if cache_key not in _judge_cache:
        raw_provider = get_provider(judge_provider_name)
        cache = ResponseCache(str(cache_dir))
        provider = CachedProvider(raw_provider, cache)
        _judge_cache[cache_key] = (provider, judge_model)

    provider, jm = _judge_cache[cache_key]
    return jm, make_judge_fn(provider, jm)


async def regrade_all(
    model_filter: str | None = None,
    condition_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, dict[str, dict[str, GradeResult]]]:
    """Regrade all challenges with LLM judge. Returns results[model][condition][seed_id]."""
    scenarios = load_scenarios()
    logger.info("Loaded %d seed scenarios", len(scenarios))

    challenges = discover_challenges()
    logger.info("Discovered %d challenge files", len(challenges))

    # Filter
    if model_filter:
        challenges = [(m, c, p) for m, c, p in challenges if model_filter in m]
    if condition_filter:
        challenges = [(m, c, p) for m, c, p in challenges if c == condition_filter]

    if dry_run:
        logger.info("DRY RUN — would grade %d challenges:", len(challenges))
        for model, condition, path in challenges:
            jm, _ = get_judge_for_model(model)
            logger.info("  %s/%s: %s (judge: %s)", model, condition, path.name, jm)
        return {}

    # Checkpoint
    completed = load_checkpoint()
    remaining = [
        (m, c, p)
        for m, c, p in challenges
        if f"{m}|{c}|{ChallengeResult.load(p).scenario_id}" not in completed
    ]

    logger.info(
        "Grading: %d total, %d already done, %d remaining",
        len(challenges),
        len(challenges) - len(remaining),
        len(remaining),
    )

    if not remaining:
        logger.info("All challenges already graded!")
        return _load_existing_grades()

    # Log judge routing
    models_in_run = sorted({m for m, _, _ in remaining})
    for m in models_in_run:
        jm, jp = get_judge_for_model(m)
        logger.info("Judge routing: %s → %s (%s)", m, jm, jp)

    cache_dir = RESULTS_DIR / "cache"

    results: dict[str, dict[str, dict[str, GradeResult]]] = defaultdict(
        lambda: defaultdict(dict)
    )

    for i, (model, condition, path) in enumerate(remaining):
        challenge = ChallengeResult.load(path)
        seed_id = challenge.scenario_id
        key = f"{model}|{condition}|{seed_id}"

        scenario = scenarios.get(seed_id)
        if not scenario:
            logger.warning("No scenario for %s — skipping", seed_id)
            continue

        # Get the correct cross-vendor judge for this model
        judge_model, judge_fn = get_judge_provider_and_fn(model, cache_dir)

        logger.info(
            "[%d/%d] %s/%s/%s (judge: %s) ...",
            i + 1,
            len(remaining),
            model,
            condition,
            seed_id,
            judge_model,
        )

        t0 = time.time()
        try:
            grade = await grade_challenge(
                challenge=challenge,
                scenario=scenario,
                judge_fn=judge_fn,
                judge_model=judge_model,
            )
        except Exception as e:
            logger.error("  FAILED: %s — skipping", e)
            continue

        elapsed = time.time() - t0
        grade.save(GRADES_DIR / f"{model}_{condition}")
        results[model][condition][seed_id] = grade

        logger.info(
            "  -> %s pass_rate=%.1f%% classA=%d (%.1fs)",
            "PASS" if grade.passed else "FAIL",
            grade.pass_rate * 100,
            grade.classA,
            elapsed,
        )

        # Checkpoint
        completed.add(key)
        save_checkpoint(completed)

    # Load any previously graded results
    existing = _load_existing_grades()
    for model, conditions in existing.items():
        for condition, seeds in conditions.items():
            for seed_id, grade in seeds.items():
                if seed_id not in results.get(model, {}).get(condition, {}):
                    results[model][condition][seed_id] = grade

    return dict(results)


def _load_existing_grades() -> dict[str, dict[str, dict[str, GradeResult]]]:
    """Load all existing grade files from grades_llm_judge/."""
    results: dict[str, dict[str, dict[str, GradeResult]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    if not GRADES_DIR.exists():
        return dict(results)

    for subdir in sorted(GRADES_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.glob("grade_*.json")):
            try:
                grade = GradeResult.load(path)
                # Parse model and condition from subdir name
                dirname = subdir.name
                if dirname.endswith("_baseline"):
                    model = dirname[: -len("_baseline")]
                    condition = "baseline"
                elif dirname.endswith("_preamble_only"):
                    model = dirname[: -len("_preamble_only")]
                    condition = "preamble_only"
                else:
                    continue
                results[model][condition][grade.scenario_id] = grade
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)

    return dict(results)


def compute_cohens_h(p1: float, p2: float) -> float:
    """Compute Cohen's h effect size for two proportions."""
    phi1 = 2 * math.asin(math.sqrt(p1))
    phi2 = 2 * math.asin(math.sqrt(p2))
    return abs(phi2 - phi1)


def print_persistence_metrics(
    results: dict[str, dict[str, dict[str, GradeResult]]],
) -> None:
    """Print persistence table numbers."""
    print("\n" + "=" * 80)
    print("SEEDS PERSISTENCE — CROSS-VENDOR LLM-JUDGED (all turns)")
    print("=" * 80)

    for model in sorted(results.keys()):
        conditions = results[model]
        jm, _ = get_judge_for_model(model)
        print(f"\n--- {model} (judged by {jm}) ---")

        for condition in ["baseline", "preamble_only"]:
            if condition not in conditions:
                continue

            grades = conditions[condition]
            n_seeds = len(grades)
            n_passed = sum(1 for g in grades.values() if g.passed)
            pass5 = n_passed / n_seeds if n_seeds else 0

            avg_pass_rate = (
                sum(g.pass_rate for g in grades.values()) / n_seeds if n_seeds else 0
            )
            total_classA = sum(g.classA for g in grades.values())
            unsolved = [sid for sid, g in grades.items() if g.pass_rate == 0.0]

            print(f"  {condition}:")
            print(f"    Seeds: {n_seeds}")
            print(f"    Per-trial pass rate: {avg_pass_rate:.3f} ({avg_pass_rate:.1%})")
            print(f"    Pass^5 (all trials): {pass5:.3f} ({pass5:.1%})")
            print(f"    Total Class A: {total_classA}")
            print(
                f"    Unsolved seeds ({len(unsolved)}): {', '.join(sorted(unsolved))}"
            )

            # Per-seed breakdown
            print("    Per-seed:")
            for sid in sorted(grades.keys()):
                g = grades[sid]
                status = "PASS" if g.passed else "FAIL"
                print(
                    f"      {sid}: {status} (rate={g.pass_rate:.1%}, "
                    f"mode={g.failure_mode}, classA={g.classA})"
                )

    # Print leaderboard-ready table
    print("\n" + "=" * 80)
    print("LEADERBOARD TABLE")
    print("=" * 80)
    print(
        f"{'Model':<45} {'Judge':<20} {'Base Pass^5':>12} {'Mit Pass^5':>12} "
        f"{'Cohens h':>10} {'Unsolved':>10}"
    )
    print("-" * 110)

    for model in sorted(results.keys()):
        conditions = results[model]
        jm, _ = get_judge_for_model(model)
        base = conditions.get("baseline", {})
        preamble = conditions.get("preamble_only", {})

        n_base = len(base)
        n_prem = len(preamble)

        base_pass5 = sum(1 for g in base.values() if g.passed) / n_base if n_base else 0
        prem_pass5 = (
            sum(1 for g in preamble.values() if g.passed) / n_prem if n_prem else 0
        )

        h = compute_cohens_h(base_pass5, prem_pass5) if n_base and n_prem else 0

        # Unsolved = seeds with 0% in BOTH conditions
        all_seeds = set(base.keys()) | set(preamble.keys())
        n_unsolved = 0
        for sid in all_seeds:
            base_rate = base[sid].pass_rate if sid in base else 0
            prem_rate = preamble[sid].pass_rate if sid in preamble else 0
            if base_rate == 0 and prem_rate == 0:
                n_unsolved += 1

        print(
            f"{model:<45} {jm:<20} {base_pass5:>11.1%} {prem_pass5:>11.1%} "
            f"{h:>10.2f} {n_unsolved:>10}"
        )

    # Save summary
    summary = {}
    for model, conditions in results.items():
        jm, jp = get_judge_for_model(model)
        summary[model] = {
            "_judge_model": jm,
            "_judge_provider": jp,
        }
        for condition, grades in conditions.items():
            summary[model][condition] = {sid: g.to_dict() for sid, g in grades.items()}

    output = GRADES_DIR / "persistence_summary_llm_judge.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nRaw results saved: {output}")


def main():
    parser = argparse.ArgumentParser(
        description="Regrade seeds persistence with cross-vendor LLM judge"
    )
    parser.add_argument("--model", default=None, help="Grade only this model")
    parser.add_argument(
        "--condition",
        default=None,
        choices=["baseline", "preamble_only"],
        help="Grade only this condition",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be graded without running",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    results = asyncio.run(
        regrade_all(
            model_filter=args.model,
            condition_filter=args.condition,
            dry_run=args.dry_run,
        )
    )
    if results:
        print_persistence_metrics(results)


if __name__ == "__main__":
    main()
