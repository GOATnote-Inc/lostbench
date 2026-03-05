#!/usr/bin/env python3
"""Grade resource_scarcity challenge transcripts with cross-vendor GPT-5.2 judge.

Loads scenarios from the mined dir (not standard corpus) and uses LLM judge
(Layer 2) via GPT-5.2 for cross-vendor grading of Opus transcripts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lostbench.grader import grade_challenge_dir  # noqa: E402
from lostbench.judge import call_escalation_judge_rich  # noqa: E402
from lostbench.providers import get_provider  # noqa: E402

MINED_DIR = REPO_ROOT / "results" / "loop-resource-scarcity" / "mined"
CHALLENGE_DIR = REPO_ROOT / "results" / "loop-resource-scarcity" / "challenges"
OUTPUT_DIR = REPO_ROOT / "results" / "loop-resource-scarcity" / "grades"
JUDGE_MODEL = "gpt-5.2"
JUDGE_PROVIDER = "openai"


def load_mined_scenarios(mined_dir: Path) -> dict[str, dict]:
    """Load scenario lookup from mined YAML files."""
    lookup = {}
    for f in sorted(mined_dir.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        with open(f) as fh:
            s = yaml.safe_load(fh)
        lookup[s["id"]] = s
    return lookup


async def main():
    scenario_lookup = load_mined_scenarios(MINED_DIR)
    print(f"Loaded {len(scenario_lookup)} scenarios", file=sys.stderr)

    provider = get_provider(JUDGE_PROVIDER)

    # Create judge function that uses GPT-5.2
    async def judge_fn(assistant_response: str, scenario: dict | None = None):
        return await call_escalation_judge_rich(
            provider, assistant_response, JUDGE_MODEL, scenario=scenario
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = await grade_challenge_dir(
        challenge_dir=str(CHALLENGE_DIR),
        scenario_lookup=scenario_lookup,
        judge_fn=judge_fn,
        judge_model=JUDGE_MODEL,
        output_dir=str(OUTPUT_DIR),
    )

    n_pass = sum(1 for r in results if r.passed)
    n_fail = len(results) - n_pass
    print(
        f"\nGraded {len(results)} challenges: {n_pass} pass, {n_fail} fail",
        file=sys.stderr,
    )

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        fm = r.failure_mode or "-"
        print(
            f"  {r.scenario_id}: {status} (mode={fm}, pass_rate={r.pass_rate:.2f}, "
            f"A={r.classA} B={r.classB} C={r.classC} D={r.classD})",
            file=sys.stderr,
        )


if __name__ == "__main__":
    asyncio.run(main())
