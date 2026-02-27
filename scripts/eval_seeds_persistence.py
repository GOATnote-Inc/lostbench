#!/usr/bin/env python3
"""Evaluate Grok and Gemini on 17 seeds (baseline + preamble, 5 trials).

Checkpoint-resume: saves after every scenario. Re-run to resume from where you left off.
Caching: all API calls are cached via ResponseCache (SHA-256 keyed).

Usage:
    python3 scripts/eval_seeds_persistence.py
    python3 scripts/eval_seeds_persistence.py --model grok-4-1-fast-reasoning-latest
    python3 scripts/eval_seeds_persistence.py --resume  # re-run to continue after drop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml

from lostbench.cache import ResponseCache
from lostbench.challenge import ChallengeResult, run_challenge
from lostbench.msiw.wrapper import MSIW_SYSTEM_PREAMBLE
from lostbench.providers import get_provider
from lostbench.providers.cached import CachedProvider

logger = logging.getLogger("eval_seeds")

# --- Configuration ---

MODELS = [
    {"model": "grok-4-1-fast-reasoning-latest", "provider": "xai"},
    {"model": "gemini-3.1-pro-preview", "provider": "google"},
    {"model": "claude-opus-4-6", "provider": "anthropic"},
    {"model": "gpt-5.2", "provider": "openai"},
]

CONDITIONS = ["baseline", "preamble_only"]

N_TRIALS = 5

SEEDS_DIR = Path(__file__).parent.parent / "seeds_mined"
OUTPUT_BASE = Path(__file__).parent.parent / "results" / "seeds-persistence"
CHECKPOINT_FILE = OUTPUT_BASE / "checkpoint.json"


def mine_seeds_if_needed(seeds_dir: Path) -> list[dict]:
    """Load mined YAML scenarios, mining from ScribeGoat2 if needed."""
    if not seeds_dir.exists() or not list(seeds_dir.glob("*.yaml")):
        logger.info("Mining seeds from ScribeGoat2...")
        sg2_seeds = Path.home() / "scribegoat2/evaluation/bloom_eval_v2/scenarios/seeds"
        if not sg2_seeds.exists():
            logger.error("ScribeGoat2 seeds not found at %s", sg2_seeds)
            sys.exit(1)
        from lostbench.mine import convert_seed_dir

        convert_seed_dir(sg2_seeds, seeds_dir)

    scenarios = []
    for path in sorted(seeds_dir.glob("*.yaml")):
        with open(path) as f:
            scenarios.append(yaml.safe_load(f))
    return scenarios


def load_checkpoint() -> dict:
    """Load checkpoint state. Returns {completed: set of "model|condition|seed_id"}."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        return {"completed": set(data.get("completed", []))}
    return {"completed": set()}


def save_checkpoint(state: dict) -> None:
    """Save checkpoint state."""
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"completed": sorted(state["completed"])}, f, indent=2)


def checkpoint_key(model: str, condition: str, seed_id: str) -> str:
    return f"{model}|{condition}|{seed_id}"


async def run_one_challenge(
    scenario: dict,
    provider: CachedProvider,
    model: str,
    condition: str,
    n_trials: int,
    output_dir: Path,
) -> ChallengeResult:
    """Run a single challenge with appropriate system prompt."""
    system_prompt = (
        MSIW_SYSTEM_PREAMBLE.strip() if condition == "preamble_only" else None
    )

    result = await run_challenge(
        scenario=scenario,
        provider=provider,
        model=model,
        n_trials=n_trials,
        system_prompt=system_prompt,
    )

    # Save with condition in filename
    output_dir.mkdir(parents=True, exist_ok=True)
    model_safe = model.replace("/", "-").replace(" ", "_")
    filename = f"challenge_{result.scenario_id}_{model_safe}_{condition}.json"
    path = output_dir / filename
    with open(path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)
    return result


async def run_eval(
    models: list[dict],
    conditions: list[str],
    n_trials: int,
    scenarios: list[dict],
) -> None:
    """Run full evaluation matrix with checkpoint-resume."""
    state = load_checkpoint()

    # Count remaining by checking actual keys, not total vs global checkpoint count
    all_keys = set()
    for model_cfg in models:
        for condition in conditions:
            for scenario in scenarios:
                all_keys.add(
                    checkpoint_key(model_cfg["model"], condition, scenario["id"])
                )
    done_keys = all_keys & state["completed"]
    remaining_keys = all_keys - state["completed"]
    total = len(all_keys)
    done = len(done_keys)
    remaining = len(remaining_keys)

    logger.info("=" * 60)
    logger.info("Seeds Persistence Evaluation")
    logger.info("=" * 60)
    logger.info("Models: %s", ", ".join(m["model"] for m in models))
    logger.info("Conditions: %s", ", ".join(conditions))
    logger.info("Seeds: %d", len(scenarios))
    logger.info("Trials: %d", n_trials)
    logger.info("Total challenges: %d (%d done, %d remaining)", total, done, remaining)
    logger.info("=" * 60)

    if remaining == 0:
        logger.info("All challenges already complete!")
        return

    for model_cfg in models:
        model = model_cfg["model"]
        provider_name = model_cfg["provider"]

        # Create cached provider per model
        cache_dir = OUTPUT_BASE / "cache"
        raw_provider = get_provider(provider_name)
        cache = ResponseCache(str(cache_dir))
        provider = CachedProvider(raw_provider, cache)

        for condition in conditions:
            out_dir = OUTPUT_BASE / f"{model_safe(model)}_{condition}"

            for scenario in scenarios:
                seed_id = scenario["id"]
                key = checkpoint_key(model, condition, seed_id)

                if key in state["completed"]:
                    continue

                logger.info(
                    "[%s/%s] %s (%d trials)...",
                    model,
                    condition,
                    seed_id,
                    n_trials,
                )

                t0 = time.time()
                try:
                    result = await run_one_challenge(
                        scenario=scenario,
                        provider=provider,
                        model=model,
                        condition=condition,
                        n_trials=n_trials,
                        output_dir=out_dir,
                    )
                    elapsed = time.time() - t0
                    n_responses = sum(len(t.responses) for t in result.transcripts)
                    logger.info(
                        "  -> %d responses in %.1fs",
                        n_responses,
                        elapsed,
                    )
                except Exception as e:
                    logger.error("  FAILED: %s — skipping, will retry on re-run", e)
                    continue

                # Checkpoint after each scenario
                state["completed"].add(key)
                save_checkpoint(state)
                done += 1
                logger.info(
                    "  Checkpoint: %d/%d complete (%.0f%%)",
                    done,
                    total,
                    100 * done / total,
                )

    logger.info("=" * 60)
    logger.info("Evaluation complete: %d/%d challenges", done, total)
    logger.info("Results: %s", OUTPUT_BASE)
    logger.info("=" * 60)


def model_safe(model: str) -> str:
    return model.replace("/", "-").replace(" ", "_")


def main():
    parser = argparse.ArgumentParser(description="Evaluate seeds persistence")
    parser.add_argument(
        "--model",
        default=None,
        help="Run only this model (default: all)",
    )
    parser.add_argument(
        "--condition",
        default=None,
        choices=CONDITIONS,
        help="Run only this condition (default: both)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=N_TRIALS,
        help=f"Trials per scenario (default: {N_TRIALS})",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint (this is the default behavior anyway)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    # Filter models if specified
    models = MODELS
    if args.model:
        models = [m for m in MODELS if m["model"] == args.model]
        if not models:
            # Try partial match
            models = [m for m in MODELS if args.model in m["model"]]
        if not models:
            logger.error("Unknown model: %s", args.model)
            logger.error("Available: %s", ", ".join(m["model"] for m in MODELS))
            sys.exit(1)

    conditions = CONDITIONS
    if args.condition:
        conditions = [args.condition]

    # Mine seeds
    scenarios = mine_seeds_if_needed(SEEDS_DIR)
    logger.info("Loaded %d seed scenarios", len(scenarios))

    asyncio.run(run_eval(models, conditions, args.trials, scenarios))


if __name__ == "__main__":
    main()
