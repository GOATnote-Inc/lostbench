#!/usr/bin/env python3
"""Cross-vendor resource_scarcity evaluation: 6 MCI scenarios × 3 models × 2 arms.

Models: GPT-5.2, Gemini 3.1 Pro, Grok 4 Fast
Judge: Opus 4.6 (cross-vendor: non-Anthropic targets use Opus judge)
Trials: 5 per scenario per arm

MTR-052 is run but excluded from EF-016 rate calculations (triage advisory,
not pressure capitulation — context misinterpretation).

Output structure:
  results/resource-scarcity-crossvendor/{model_slug}/
    challenges/     — baseline transcripts
    preamble/       — preamble-arm transcripts
    grades/baseline/ — graded baseline
    grades/preamble/ — graded preamble

Reuses infrastructure: run_challenge, grade_challenge_dir, CachedProvider.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lostbench.cache import ResponseCache  # noqa: E402
from lostbench.challenge import run_challenge  # noqa: E402
from lostbench.grader import grade_challenge_dir  # noqa: E402
from lostbench.judge import call_escalation_judge_rich  # noqa: E402
from lostbench.msiw.wrapper import MSIW_SYSTEM_PREAMBLE  # noqa: E402
from lostbench.providers import get_provider  # noqa: E402
from lostbench.providers.cached import CachedProvider  # noqa: E402
from lostbench.scenarios.loader import load_scenarios  # noqa: E402

MODELS = [
    {"model": "gpt-5.2", "provider": "openai", "slug": "gpt-5.2"},
    {"model": "gemini-3.1-pro-preview", "provider": "google", "slug": "gemini-3.1-pro"},
    {"model": "grok-4-fast-reasoning", "provider": "xai", "slug": "grok-4-fast"},
]

SCENARIO_IDS = ["MTR-051", "MTR-052", "MTR-053", "MTR-054", "MTR-055", "MTR-056"]
EXCLUDED_FROM_EF016 = {"MTR-052"}  # triage advisory, not pressure capitulation
TRIALS = 5

# Cross-vendor judge: Opus judges all non-Anthropic models
JUDGE_MODEL = "claude-opus-4-6"
JUDGE_PROVIDER = "anthropic"

RESULTS_ROOT = REPO_ROOT / "results" / "resource-scarcity-crossvendor"


def model_dir(slug: str) -> Path:
    return RESULTS_ROOT / slug


async def run_arm(
    scenarios: list[dict],
    model_cfg: dict,
    output_dir: Path,
    system_prompt: str | None = None,
    arm_label: str = "baseline",
):
    """Run one arm (baseline or preamble) for all scenarios on one model."""
    raw_provider = get_provider(model_cfg["provider"])
    cache = ResponseCache(str(output_dir))
    provider = CachedProvider(raw_provider, cache)
    model = model_cfg["model"]

    output_dir.mkdir(parents=True, exist_ok=True)

    for scenario in scenarios:
        sid = scenario["id"]
        existing = output_dir / f"challenge_{sid}_{model}.json"
        if existing.exists():
            print(
                f"  [{model_cfg['slug']}/{arm_label}] Skipping {sid} (exists)",
                file=sys.stderr,
            )
            continue
        print(
            f"  [{model_cfg['slug']}/{arm_label}] Challenge: {sid} x {TRIALS} trials",
            file=sys.stderr,
        )
        try:
            result = await run_challenge(
                scenario=scenario,
                provider=provider,
                model=model,
                n_trials=TRIALS,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            # Handle provider content filters (e.g., xAI 403 SAFETY_CHECK)
            if "403" in str(exc) or "PermissionDenied" in type(exc).__name__:
                print(
                    f"  [{model_cfg['slug']}/{arm_label}] BLOCKED by content filter: "
                    f"{sid} — skipping",
                    file=sys.stderr,
                )
                continue
            raise
        path = result.save(str(output_dir))
        print(f"  [{model_cfg['slug']}/{arm_label}] Saved -> {path}", file=sys.stderr)


async def grade_arm(
    model_cfg: dict,
    challenge_dir: Path,
    output_dir: Path,
    scenario_lookup: dict[str, dict],
    arm_label: str = "baseline",
):
    """Grade one arm's transcripts with cross-vendor judge."""
    if not challenge_dir.exists():
        print(
            f"  [{model_cfg['slug']}/{arm_label}] No challenge dir, skipping",
            file=sys.stderr,
        )
        return []

    judge_provider = get_provider(JUDGE_PROVIDER)

    async def judge_fn(assistant_response: str, scenario: dict | None = None):
        return await call_escalation_judge_rich(
            judge_provider, assistant_response, JUDGE_MODEL, scenario=scenario
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    results = await grade_challenge_dir(
        challenge_dir=str(challenge_dir),
        scenario_lookup=scenario_lookup,
        judge_fn=judge_fn,
        judge_model=JUDGE_MODEL,
        output_dir=str(output_dir),
    )

    n_pass = sum(1 for r in results if r.passed)
    n_fail = len(results) - n_pass
    print(
        f"  [{model_cfg['slug']}/{arm_label}] Graded {len(results)}: "
        f"{n_pass} pass, {n_fail} fail",
        file=sys.stderr,
    )
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        excluded = (
            " [EXCLUDED from EF-016]" if r.scenario_id in EXCLUDED_FROM_EF016 else ""
        )
        print(
            f"    {r.scenario_id}: {status} (pass_rate={r.pass_rate:.2f}, "
            f"A={r.classA} D={r.classD}){excluded}",
            file=sys.stderr,
        )
    return results


def compute_ef016_rate(results: list, excluded: set[str]) -> dict:
    """Compute EF-016 pass rate excluding triage advisory scenarios."""
    included = [r for r in results if r.scenario_id not in excluded]
    if not included:
        return {"pass_rate": None, "n_scenarios": 0, "n_pass": 0}
    n_pass = sum(1 for r in included if r.passed)
    return {
        "pass_rate": round(n_pass / len(included), 3),
        "n_scenarios": len(included),
        "n_pass": n_pass,
        "n_fail": len(included) - n_pass,
        "per_scenario": {
            r.scenario_id: {
                "pass": r.passed,
                "pass_rate": r.pass_rate,
                "classA": r.classA,
                "classD": r.classD,
            }
            for r in included
        },
    }


def build_summary(all_results: dict) -> dict:
    """Build cross-vendor comparison summary."""
    summary = {"models": {}, "ef016_comparison": []}

    for model_slug, arms in all_results.items():
        model_summary = {}
        for arm_label, results in arms.items():
            ef016 = compute_ef016_rate(results, EXCLUDED_FROM_EF016)
            all_rate = {
                r.scenario_id: {"pass": r.passed, "pass_rate": r.pass_rate}
                for r in results
            }
            model_summary[arm_label] = {
                "ef016": ef016,
                "all_scenarios": all_rate,
            }
        summary["models"][model_slug] = model_summary

        # EF-016 comparison row
        baseline_ef016 = model_summary.get("baseline", {}).get("ef016", {})
        preamble_ef016 = model_summary.get("preamble", {}).get("ef016", {})
        summary["ef016_comparison"].append(
            {
                "model": model_slug,
                "baseline_pass_rate": baseline_ef016.get("pass_rate"),
                "preamble_pass_rate": preamble_ef016.get("pass_rate"),
                "baseline_n_fail": baseline_ef016.get("n_fail"),
                "preamble_n_fail": preamble_ef016.get("n_fail"),
            }
        )

    return summary


def print_summary_table(summary: dict):
    """Print comparison table to stderr."""
    print("\n" + "=" * 72, file=sys.stderr)
    print("CROSS-VENDOR RESOURCE SCARCITY COMPARISON (EF-016)", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print(
        f"{'Model':<25} {'Baseline':>10} {'Preamble':>10} {'BL Fail':>8} {'PR Fail':>8}",
        file=sys.stderr,
    )
    print("-" * 72, file=sys.stderr)

    # Include Opus from Track B for comparison
    print(
        f"{'claude-opus-4-6 (Track B)':<25} {'33%':>10} {'60%':>10} {'4':>8} {'2':>8}",
        file=sys.stderr,
    )

    for row in summary["ef016_comparison"]:
        bl = (
            f"{row['baseline_pass_rate']:.0%}"
            if row["baseline_pass_rate"] is not None
            else "N/A"
        )
        pr = (
            f"{row['preamble_pass_rate']:.0%}"
            if row["preamble_pass_rate"] is not None
            else "N/A"
        )
        bl_f = str(row.get("baseline_n_fail", "?"))
        pr_f = str(row.get("preamble_n_fail", "?"))
        print(
            f"{row['model']:<25} {bl:>10} {pr:>10} {bl_f:>8} {pr_f:>8}", file=sys.stderr
        )

    print("-" * 72, file=sys.stderr)
    print("Note: MTR-052 excluded from EF-016 (triage advisory)", file=sys.stderr)
    print(
        "Note: Opus Track B data from results/resource-scarcity-repro/", file=sys.stderr
    )
    print("Judge: claude-opus-4-6 (cross-vendor)\n", file=sys.stderr)


async def main():
    scenarios = load_scenarios(corpus="emergency", conditions=SCENARIO_IDS)
    scenario_lookup = {s["id"]: s for s in scenarios}
    print(
        f"Loaded {len(scenarios)} scenarios: " + ", ".join(s["id"] for s in scenarios),
        file=sys.stderr,
    )
    if len(scenarios) != len(SCENARIO_IDS):
        missing = set(SCENARIO_IDS) - {s["id"] for s in scenarios}
        print(f"WARNING: Missing scenarios: {missing}", file=sys.stderr)

    all_results: dict[str, dict[str, list]] = {}

    for model_cfg in MODELS:
        slug = model_cfg["slug"]
        mdir = model_dir(slug)
        print(f"\n{'=' * 50}", file=sys.stderr)
        print(f"Model: {model_cfg['model']} ({model_cfg['provider']})", file=sys.stderr)
        print(f"{'=' * 50}", file=sys.stderr)

        # Challenge phase
        challenge_dir = mdir / "challenges"
        preamble_dir = mdir / "preamble"

        print(f"\n--- Baseline arm ({TRIALS} trials) ---", file=sys.stderr)
        await run_arm(
            scenarios,
            model_cfg,
            challenge_dir,
            system_prompt=None,
            arm_label="baseline",
        )

        print(f"\n--- Preamble arm ({TRIALS} trials) ---", file=sys.stderr)
        await run_arm(
            scenarios,
            model_cfg,
            preamble_dir,
            system_prompt=MSIW_SYSTEM_PREAMBLE,
            arm_label="preamble",
        )

        # Grading phase
        grade_baseline_dir = mdir / "grades" / "baseline"
        grade_preamble_dir = mdir / "grades" / "preamble"

        print("\n--- Grading baseline ---", file=sys.stderr)
        baseline_results = await grade_arm(
            model_cfg, challenge_dir, grade_baseline_dir, scenario_lookup, "baseline"
        )

        print("\n--- Grading preamble ---", file=sys.stderr)
        preamble_results = await grade_arm(
            model_cfg, preamble_dir, grade_preamble_dir, scenario_lookup, "preamble"
        )

        all_results[slug] = {
            "baseline": baseline_results,
            "preamble": preamble_results,
        }

    # Summary
    summary = build_summary(all_results)
    print_summary_table(summary)

    # Save summary
    summary_path = RESULTS_ROOT / "crossvendor_summary.json"
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    # Serialize GradeResult references to dicts for JSON
    serializable_summary = json.loads(json.dumps(summary, default=str))
    with open(summary_path, "w") as f:
        json.dump(serializable_summary, f, indent=2)
    print(f"Summary written to {summary_path}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
