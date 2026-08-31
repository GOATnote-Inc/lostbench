"""Pre-run cost estimation and budget enforcement for ``max_cost_usd``.

The budget gate runs BEFORE the first API call: it estimates the run's cost
from ``configs/model_pricing.yaml`` (scenarios x trials x per-challenge
target + judge cost) and blocks the run if the estimate exceeds the
configured ``max_cost_usd``.

Fail-closed: if a budget is configured but the pricing data is missing or
the model has no pricing entry, the run is blocked — a budget that cannot
be enforced is treated as exceeded, never silently ignored.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_PRICING_PATH = Path("configs/model_pricing.yaml")


class BudgetError(RuntimeError):
    """Budget enforcement failure.

    Raised when the estimated cost exceeds ``max_cost_usd``, or when a
    budget is configured but cannot be enforced (missing pricing file,
    model without a pricing entry).
    """


def load_model_pricing(path: str | Path | None = None) -> dict:
    """Load per-model pricing from the pricing YAML.

    Returns the ``models`` mapping. Raises :class:`BudgetError` if the file
    is missing or contains no models — enforcement must not silently
    degrade to "no budget".
    """
    pricing_path = Path(path) if path is not None else DEFAULT_PRICING_PATH
    if not pricing_path.exists():
        raise BudgetError(
            f"pricing file not found: {pricing_path} — cannot enforce "
            "max_cost_usd without pricing data"
        )
    with open(pricing_path) as f:
        raw = yaml.safe_load(f)
    models = (raw or {}).get("models")
    if not isinstance(models, dict) or not models:
        raise BudgetError(f"no models defined in pricing file: {pricing_path}")
    return models


def _pricing_entry(model: str, models: dict) -> dict:
    """Find the pricing entry for a model ID (tolerating dated aliases)."""
    entry = models.get(model)
    if entry is None:
        # A dated alias like claude-opus-4-6-20250918 matches the base ID.
        for known, candidate in models.items():
            if model.startswith(known):
                entry = candidate
                break
    if entry is None:
        raise BudgetError(
            f"model '{model}' has no entry in the pricing file — add it to "
            "configs/model_pricing.yaml (or remove max_cost_usd to run "
            "without a budget gate)"
        )
    return entry


def cost_per_challenge_usd(model: str, models: dict) -> float:
    """Estimated cost of one scenario-trial for one model.

    Uses ``avg_tokens_per_challenge`` (observed, split evenly between input
    and output) and the per-1M-token rates from the pricing file.
    """
    entry = _pricing_entry(model, models)
    try:
        avg_tokens = float(entry.get("avg_tokens_per_challenge", 4000))
        input_rate = float(entry["input_per_1m"])
        output_rate = float(entry["output_per_1m"])
    except (KeyError, TypeError, ValueError) as e:
        raise BudgetError(f"malformed pricing entry for model '{model}': {e}") from e
    half = avg_tokens / 2.0
    return (half / 1_000_000.0) * input_rate + (half / 1_000_000.0) * output_rate


def estimate_run_cost_usd(
    model: str,
    judge_model: str | None,
    n_scenarios: int,
    n_trials: int,
    pricing_path: str | Path | None = None,
) -> float:
    """Estimate total run cost before the first API call.

    Every scenario-trial costs one target-model challenge plus (when a
    judge is configured) one judge challenge of graded turns.
    """
    models = load_model_pricing(pricing_path)
    per_trial = cost_per_challenge_usd(model, models)
    if judge_model:
        per_trial += cost_per_challenge_usd(judge_model, models)
    return n_scenarios * n_trials * per_trial


def enforce_budget(estimated_cost_usd: float, max_cost_usd: float) -> None:
    """Raise :class:`BudgetError` if the estimate exceeds the budget."""
    if estimated_cost_usd > max_cost_usd:
        raise BudgetError(
            f"estimated cost ${estimated_cost_usd:.2f} exceeds max_cost_usd "
            f"${max_cost_usd:.2f} — BLOCK (no API calls made). Reduce the "
            "scenario count or trials, or raise max_cost_usd."
        )
