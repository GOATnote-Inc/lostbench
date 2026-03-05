#!/usr/bin/env python3
"""Reproduce resource_scarcity finding: MTR-051–056 × 5 trials on Opus 4.6.

Runs two arms in sequence:
  1. Baseline (no preamble) → results/resource-scarcity-repro/challenges/
  2. Preamble (MSIW preamble) → results/resource-scarcity-repro/preamble/

Loads scenarios from the standard emergency corpus (tier1/).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lostbench.cache import ResponseCache  # noqa: E402
from lostbench.challenge import run_challenge  # noqa: E402
from lostbench.msiw.wrapper import MSIW_SYSTEM_PREAMBLE  # noqa: E402
from lostbench.providers import get_provider  # noqa: E402
from lostbench.providers.cached import CachedProvider  # noqa: E402
from lostbench.scenarios.loader import load_scenarios  # noqa: E402

SCENARIO_IDS = ["MTR-051", "MTR-052", "MTR-053", "MTR-054", "MTR-055", "MTR-056"]
MODEL = "claude-opus-4-6"
PROVIDER = "anthropic"
TRIALS = 5

BASELINE_DIR = REPO_ROOT / "results" / "resource-scarcity-repro" / "challenges"
PREAMBLE_DIR = REPO_ROOT / "results" / "resource-scarcity-repro" / "preamble"


async def run_arm(
    scenarios: list[dict],
    output_dir: Path,
    system_prompt: str | None = None,
    arm_label: str = "baseline",
):
    """Run one arm (baseline or preamble) for all scenarios."""
    raw_provider = get_provider(PROVIDER)
    cache = ResponseCache(str(output_dir))
    provider = CachedProvider(raw_provider, cache)

    output_dir.mkdir(parents=True, exist_ok=True)

    for scenario in scenarios:
        sid = scenario["id"]
        existing = output_dir / f"challenge_{sid}_{MODEL}.json"
        if existing.exists():
            print(f"  [{arm_label}] Skipping {sid} (already exists)", file=sys.stderr)
            continue
        print(
            f"  [{arm_label}] Challenge: {sid} x {TRIALS} trials ({MODEL})",
            file=sys.stderr,
        )
        result = await run_challenge(
            scenario=scenario,
            provider=provider,
            model=MODEL,
            n_trials=TRIALS,
            system_prompt=system_prompt,
        )
        path = result.save(str(output_dir))
        print(f"  [{arm_label}] Saved -> {path}", file=sys.stderr)


async def main():
    scenarios = load_scenarios(corpus="emergency", conditions=SCENARIO_IDS)
    print(
        f"Loaded {len(scenarios)} scenarios: " + ", ".join(s["id"] for s in scenarios),
        file=sys.stderr,
    )
    if len(scenarios) != len(SCENARIO_IDS):
        missing = set(SCENARIO_IDS) - {s["id"] for s in scenarios}
        print(f"WARNING: Missing scenarios: {missing}", file=sys.stderr)

    # Arm 1: Baseline
    print(f"\n=== Baseline arm ({TRIALS} trials each) ===", file=sys.stderr)
    await run_arm(scenarios, BASELINE_DIR, system_prompt=None, arm_label="baseline")

    # Arm 2: Preamble
    print(f"\n=== Preamble arm ({TRIALS} trials each) ===", file=sys.stderr)
    await run_arm(
        scenarios,
        PREAMBLE_DIR,
        system_prompt=MSIW_SYSTEM_PREAMBLE,
        arm_label="preamble",
    )

    print("\nAll arms complete.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
