"""Checkpoint/resume support for LostBench runs."""

import hashlib
import json
import logging
import os
from pathlib import Path

from lostbench import __version__
from lostbench.config import RunConfig

logger = logging.getLogger(__name__)


CHECKPOINT_FILENAME = ".lostbench_checkpoint.json"


def _config_key_fields(config: RunConfig) -> dict:
    """Extract config fields that affect evaluation behavior."""
    return {
        "model": config.model,
        "provider": config.provider,
        "trials": config.trials,
        "system_prompt_hash": config.system_prompt_hash,
        "judge_model": config.resolved_judge_model,
        "corpus": config.corpus,
        "pattern_only": config.pattern_only,
        "temperature": config.temperature,
        "seed": config.seed,
        "wrapper_enabled": config.wrapper_enabled,
        "wrapper_preamble": config.wrapper_preamble,
        "inject_preamble": config.inject_preamble,
    }


def config_hash(config: RunConfig) -> str:
    """Deterministic hash of config fields that affect evaluation behavior."""
    serialized = json.dumps(_config_key_fields(config), sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def checkpoint_path(output_dir: str) -> Path:
    return Path(output_dir) / CHECKPOINT_FILENAME


def save_checkpoint(
    output_dir: str,
    dataset_hash: str,
    cfg: RunConfig,
    completed_scenario_ids: list[str],
    scenario_results: list[dict],
    *,
    in_progress_scenario: dict | None = None,
) -> None:
    """Write checkpoint after each completed scenario or trial.

    Args:
        in_progress_scenario: Partial trial results for a scenario still running.
            Keys: scenario_id, completed_trials (list of trial result dicts).
            Cleared when the scenario finishes and moves to completed_scenario_ids.
    """
    data = {
        "lostbench_version": __version__,
        "dataset_hash": dataset_hash,
        "config_hash": config_hash(cfg),
        "config_fields": _config_key_fields(cfg),
        "corpus": cfg.corpus,
        "model": cfg.model,
        "provider": cfg.provider,
        "trials": cfg.trials,
        "completed_scenario_ids": completed_scenario_ids,
        "scenario_results": scenario_results,
    }
    if in_progress_scenario:
        data["in_progress_scenario"] = in_progress_scenario
    path = checkpoint_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(tmp, path)


def load_checkpoint(
    output_dir: str, dataset_hash: str, cfg: RunConfig
) -> tuple[list[str], list[dict], dict | None] | None:
    """Load checkpoint if valid. Returns (completed_ids, scenario_results) or None."""
    path = checkpoint_path(output_dir)
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    if data.get("dataset_hash") != dataset_hash:
        logger.warning("Dataset hash mismatch — starting fresh.")
        return None

    if data.get("config_hash") != config_hash(cfg):
        # Identify which fields changed for debugging
        saved_fields = data.get("config_fields", {})
        current_fields = _config_key_fields(cfg)
        changed = [
            k for k in current_fields
            if saved_fields.get(k) != current_fields[k]
        ] if saved_fields else ["(saved checkpoint has no field detail)"]
        logger.warning(
            "Config mismatch — starting fresh. Changed: %s",
            ", ".join(changed),
        )
        return None

    completed = data.get("completed_scenario_ids", [])
    results = data.get("scenario_results", [])
    in_progress = data.get("in_progress_scenario")
    trial_count = len(in_progress["completed_trials"]) if in_progress else 0
    logger.info(
        "Resuming — %d scenarios completed%s.",
        len(completed),
        f", 1 in-progress ({trial_count} trials done)" if in_progress else "",
    )
    return (completed, results, in_progress)


def clear_checkpoint(output_dir: str) -> None:
    """Remove checkpoint file after successful run completion."""
    path = checkpoint_path(output_dir)
    if path.exists():
        path.unlink()
