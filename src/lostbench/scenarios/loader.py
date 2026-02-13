"""Scenario loader for LostBench."""

import hashlib
import json
from pathlib import Path

import yaml

from lostbench.config import SCENARIOS_DIR


EXCLUDED_OUTPUT_FIELDS = {"time_to_harm", "mortality_if_delayed"}


def load_scenarios(corpus: str = "emergency", conditions: list[str] | None = None) -> list[dict]:
    """Load scenario YAML files for a given corpus."""
    if corpus == "emergency":
        scenario_dir = SCENARIOS_DIR / "tier1"
    elif corpus == "crisis-resource":
        scenario_dir = SCENARIOS_DIR / "tier1_crisis"
    else:
        raise ValueError(f"Unknown corpus: {corpus}")

    scenarios = []
    for yaml_path in sorted(scenario_dir.glob("*.yaml")):
        with open(yaml_path) as f:
            scenario = yaml.safe_load(f)
        scenarios.append(scenario)

    if conditions:
        scenarios = [s for s in scenarios if s["id"] in conditions]

    return scenarios


def scenario_for_output(scenario: dict) -> dict:
    """Return scenario dict with excluded fields removed."""
    return {k: v for k, v in scenario.items() if k not in EXCLUDED_OUTPUT_FIELDS}


def compute_dataset_hash(scenarios: list[dict]) -> str:
    """Compute deterministic hash of all scenario content."""
    serialized = json.dumps(scenarios, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
