#!/usr/bin/env python3
"""Run resource_scarcity challenge: 3 mined scenarios × 5 trials on Opus 4.6.

Loads scenarios directly from the mined YAML files rather than the standard
corpus directories.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lostbench.cache import ResponseCache  # noqa: E402
from lostbench.challenge import run_challenge  # noqa: E402
from lostbench.providers import get_provider  # noqa: E402
from lostbench.providers.cached import CachedProvider  # noqa: E402

MINED_DIR = REPO_ROOT / "results" / "loop-resource-scarcity" / "mined"
OUTPUT_DIR = REPO_ROOT / "results" / "loop-resource-scarcity" / "challenges"
MODEL = "claude-opus-4-6"
PROVIDER = "anthropic"
TRIALS = 5


def load_mined_scenarios(mined_dir: Path) -> list[dict]:
    """Load all non-manifest YAML files from mined dir."""
    scenarios = []
    for f in sorted(mined_dir.glob("*.yaml")):
        if f.name.startswith("_"):
            continue
        with open(f) as fh:
            scenarios.append(yaml.safe_load(fh))
    return scenarios


async def main():
    raw_provider = get_provider(PROVIDER)
    cache = ResponseCache(str(OUTPUT_DIR))
    provider = CachedProvider(raw_provider, cache)

    scenarios = load_mined_scenarios(MINED_DIR)
    print(f"Loaded {len(scenarios)} scenarios from {MINED_DIR}", file=sys.stderr)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for scenario in scenarios:
        sid = scenario["id"]
        existing = OUTPUT_DIR / f"challenge_{sid}_{MODEL}.json"
        if existing.exists():
            print(f"\nSkipping {sid} (already exists)", file=sys.stderr)
            continue
        print(f"\nChallenge: {sid} x {TRIALS} trials ({MODEL})", file=sys.stderr)
        result = await run_challenge(
            scenario=scenario,
            provider=provider,
            model=MODEL,
            n_trials=TRIALS,
        )
        path = result.save(str(OUTPUT_DIR))
        print(f"  Saved -> {path}", file=sys.stderr)

        print(f"  {result.n_trials} trials completed", file=sys.stderr)

    print(f"\nAll challenges complete -> {OUTPUT_DIR}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
