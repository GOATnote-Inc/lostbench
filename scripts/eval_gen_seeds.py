#!/usr/bin/env python3
"""Evaluate generated seeds: GPT-5.2 + Opus 4.6, baseline + preamble, n=5.

Checkpoint-resume: saves after every scenario. Re-run to resume.
Caching: all API calls cached via ResponseCache.

Usage:
    python3 scripts/eval_gen_seeds.py
    python3 scripts/eval_gen_seeds.py --model gpt-5.2
    python3 scripts/eval_gen_seeds.py --condition baseline
    python3 scripts/eval_gen_seeds.py --trials 3
    python3 scripts/eval_gen_seeds.py --seeds-dir seeds_generated/eval_batch --output-dir results/seeds-cycle-eval
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

import yaml

from lostbench.cache import ResponseCache
from lostbench.challenge import ChallengeResult, run_challenge
from lostbench.msiw.wrapper import MSIW_SYSTEM_PREAMBLE
from lostbench.providers import get_provider
from lostbench.providers.cached import CachedProvider

logger = logging.getLogger("eval_gen_seeds")

# --- Configuration ---

MODELS = [
    {"model": "claude-opus-4-6", "provider": "anthropic"},
    {"model": "gpt-5.2", "provider": "openai"},
]

CONDITIONS = ["baseline", "preamble_only"]

N_TRIALS = 5

DEFAULT_SEEDS_DIR = Path(__file__).parent.parent / "seeds_generated"
DEFAULT_OUTPUT_BASE = Path(__file__).parent.parent / "results" / "seeds-gen-eval"


def load_seeds(seeds_dir: Path) -> list[dict]:
    """Load generated seed YAMLs (gen-*.yaml or cyc-*.yaml)."""
    if not seeds_dir.exists():
        logger.error("Seeds directory not found: %s", seeds_dir)
        sys.exit(1)
    scenarios = []
    for path in sorted(seeds_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        with open(path) as f:
            scenarios.append(yaml.safe_load(f))
    if not scenarios:
        logger.error("No seed YAML files found in %s", seeds_dir)
        sys.exit(1)
    return scenarios


def load_checkpoint(checkpoint_file: Path) -> dict:
    if checkpoint_file.exists():
        with open(checkpoint_file) as f:
            data = json.load(f)
        return {"completed": set(data.get("completed", []))}
    return {"completed": set()}


def save_checkpoint(state: dict, checkpoint_file: Path) -> None:
    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_file, "w") as f:
        json.dump({"completed": sorted(state["completed"])}, f, indent=2)


def checkpoint_key(model: str, condition: str, seed_id: str) -> str:
    return f"{model}|{condition}|{seed_id}"


def model_safe(model: str) -> str:
    return model.replace("/", "-").replace(" ", "_")


async def run_one_challenge(
    scenario: dict,
    provider: CachedProvider,
    model: str,
    condition: str,
    n_trials: int,
    output_dir: Path,
    temperature: float = 0.0,
) -> ChallengeResult:
    system_prompt = (
        MSIW_SYSTEM_PREAMBLE.strip() if condition == "preamble_only" else None
    )

    result = await run_challenge(
        scenario=scenario,
        provider=provider,
        model=model,
        n_trials=n_trials,
        temperature=temperature,
        system_prompt=system_prompt,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    msafe = model_safe(model)
    filename = f"challenge_{result.scenario_id}_{msafe}_{condition}.json"
    path = output_dir / filename
    with open(path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)
    return result


async def run_eval(
    models: list[dict],
    conditions: list[str],
    n_trials: int,
    scenarios: list[dict],
    output_base: Path = DEFAULT_OUTPUT_BASE,
    temperature: float = 0.0,
) -> None:
    checkpoint_file = output_base / "checkpoint.json"
    state = load_checkpoint(checkpoint_file)

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

    logger.info("=" * 60)
    logger.info("Generated Seeds Evaluation")
    logger.info("=" * 60)
    logger.info("Models: %s", ", ".join(m["model"] for m in models))
    logger.info("Conditions: %s", ", ".join(conditions))
    logger.info("Seeds: %d", len(scenarios))
    logger.info("Trials: %d", n_trials)
    logger.info("Temperature: %.1f", temperature)
    logger.info(
        "Total challenges: %d (%d done, %d remaining)",
        total,
        done,
        len(remaining_keys),
    )
    logger.info("=" * 60)

    if not remaining_keys:
        logger.info("All challenges already complete!")
        return

    for model_cfg in models:
        model = model_cfg["model"]
        provider_name = model_cfg["provider"]

        cache_dir = output_base / "cache"
        raw_provider = get_provider(provider_name)
        cache = ResponseCache(str(cache_dir))
        provider = CachedProvider(raw_provider, cache)

        for condition in conditions:
            out_dir = output_base / f"{model_safe(model)}_{condition}"

            for scenario in scenarios:
                seed_id = scenario["id"]
                key = checkpoint_key(model, condition, seed_id)

                if key in state["completed"]:
                    continue

                logger.info(
                    "[%s/%s] %s — %s (%d trials)...",
                    model,
                    condition,
                    seed_id,
                    scenario.get("condition", "?"),
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
                        temperature=temperature,
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

                state["completed"].add(key)
                save_checkpoint(state, checkpoint_file)
                done += 1
                logger.info(
                    "  Checkpoint: %d/%d complete (%.0f%%)",
                    done,
                    total,
                    100 * done / total,
                )

    logger.info("=" * 60)
    logger.info("Evaluation complete: %d/%d challenges", done, total)
    logger.info("Results: %s", output_base)
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate generated seeds (GPT-5.2 + Opus 4.6)"
    )
    parser.add_argument("--model", default=None, help="Run only this model")
    parser.add_argument(
        "--condition",
        default=None,
        choices=CONDITIONS,
        help="Run only this condition",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=N_TRIALS,
        help=f"Trials per scenario (default: {N_TRIALS})",
    )
    parser.add_argument(
        "--seeds-dir",
        type=Path,
        default=DEFAULT_SEEDS_DIR,
        help=f"Directory containing seed YAMLs (default: {DEFAULT_SEEDS_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_BASE,
        help=f"Output directory for results (default: {DEFAULT_OUTPUT_BASE})",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (0.0=deterministic, 0.7=stochastic)",
    )
    parser.add_argument(
        "--phase2-seeds",
        type=str,
        default=None,
        help="Path to phase1_screen.json — only eval discriminative seeds",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    models = MODELS
    if args.model:
        models = [m for m in MODELS if m["model"] == args.model]
        if not models:
            models = [m for m in MODELS if args.model in m["model"]]
        if not models:
            logger.error("Unknown model: %s", args.model)
            logger.error("Available: %s", ", ".join(m["model"] for m in MODELS))
            sys.exit(1)

    conditions = CONDITIONS
    if args.condition:
        conditions = [args.condition]

    scenarios = load_seeds(args.seeds_dir)
    logger.info("Loaded %d generated seed scenarios", len(scenarios))

    if args.phase2_seeds:
        with open(args.phase2_seeds) as f:
            screen = json.load(f)
        disc_ids = set(screen["discriminative_seeds"])
        scenarios = [s for s in scenarios if s["id"] in disc_ids]
        logger.info(
            "Phase 2: %d discriminative seeds from %s",
            len(scenarios),
            args.phase2_seeds,
        )

    asyncio.run(
        run_eval(
            models,
            conditions,
            args.trials,
            scenarios,
            args.output_dir,
            temperature=args.temperature,
        )
    )


if __name__ == "__main__":
    main()
