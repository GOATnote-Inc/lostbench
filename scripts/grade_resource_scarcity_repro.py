#!/usr/bin/env python3
"""Grade resource_scarcity repro transcripts with cross-vendor GPT-5.2 judge.

Grades both baseline and preamble arms from:
  results/resource-scarcity-repro/challenges/
  results/resource-scarcity-repro/preamble/

Outputs to:
  results/resource-scarcity-repro/grades/baseline/
  results/resource-scarcity-repro/grades/preamble/
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lostbench.grader import grade_challenge_dir  # noqa: E402
from lostbench.judge import call_escalation_judge_rich  # noqa: E402
from lostbench.providers import get_provider  # noqa: E402
from lostbench.scenarios.loader import load_scenarios  # noqa: E402

SCENARIO_IDS = ["MTR-051", "MTR-052", "MTR-053", "MTR-054", "MTR-055", "MTR-056"]
JUDGE_MODEL = "gpt-5.2"
JUDGE_PROVIDER = "openai"

RESULTS_ROOT = REPO_ROOT / "results" / "resource-scarcity-repro"

ARMS = {
    "baseline": {
        "challenge_dir": RESULTS_ROOT / "challenges",
        "output_dir": RESULTS_ROOT / "grades" / "baseline",
    },
    "preamble": {
        "challenge_dir": RESULTS_ROOT / "preamble",
        "output_dir": RESULTS_ROOT / "grades" / "preamble",
    },
}


def build_scenario_lookup(scenarios: list[dict]) -> dict[str, dict]:
    """Build ID -> scenario lookup from standard corpus."""
    return {s["id"]: s for s in scenarios}


async def grade_arm(
    arm_label: str,
    challenge_dir: Path,
    output_dir: Path,
    scenario_lookup: dict[str, dict],
):
    """Grade one arm's challenge transcripts."""
    if not challenge_dir.exists():
        print(f"  [{arm_label}] No challenge dir found, skipping", file=sys.stderr)
        return []

    provider = get_provider(JUDGE_PROVIDER)

    async def judge_fn(assistant_response: str, scenario: dict | None = None):
        return await call_escalation_judge_rich(
            provider, assistant_response, JUDGE_MODEL, scenario=scenario
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
        f"  [{arm_label}] Graded {len(results)}: {n_pass} pass, {n_fail} fail",
        file=sys.stderr,
    )

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        fm = r.failure_mode or "-"
        print(
            f"    {r.scenario_id}: {status} (mode={fm}, pass_rate={r.pass_rate:.2f}, "
            f"A={r.classA} B={r.classB} C={r.classC} D={r.classD})",
            file=sys.stderr,
        )

    return results


async def main():
    scenarios = load_scenarios(corpus="emergency", conditions=SCENARIO_IDS)
    scenario_lookup = build_scenario_lookup(scenarios)
    print(f"Loaded {len(scenario_lookup)} scenarios for grading", file=sys.stderr)

    all_results = {}
    for arm_label, dirs in ARMS.items():
        print(f"\n=== Grading {arm_label} arm ===", file=sys.stderr)
        results = await grade_arm(
            arm_label=arm_label,
            challenge_dir=dirs["challenge_dir"],
            output_dir=dirs["output_dir"],
            scenario_lookup=scenario_lookup,
        )
        all_results[arm_label] = results

    # Summary
    print("\n=== Summary ===", file=sys.stderr)
    for arm_label, results in all_results.items():
        if not results:
            continue
        n_pass = sum(1 for r in results if r.passed)
        n_total = len(results)
        rate = n_pass / n_total if n_total else 0
        print(f"  {arm_label}: {n_pass}/{n_total} pass ({rate:.0%})", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
