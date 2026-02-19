"""Scenario loader for LostBench."""

import hashlib
import json

import yaml

from lostbench.config import SCENARIOS_DIR


def load_scenarios(corpus: str = "emergency", conditions: list[str] | None = None) -> list[dict]:
    """Load scenario YAML files for a given corpus."""
    if corpus == "emergency":
        scenario_dir = SCENARIOS_DIR / "tier1"
    elif corpus == "crisis-resource":
        scenario_dir = SCENARIOS_DIR / "tier1_crisis"
    elif corpus == "defer":
        scenario_dir = SCENARIOS_DIR / "defer"
    else:
        raise ValueError(f"Unknown corpus: {corpus}")

    required_fields = {"id", "condition", "initial"}
    scenarios = []
    for yaml_path in sorted(scenario_dir.glob("*.yaml")):
        with open(yaml_path) as f:
            scenario = yaml.safe_load(f)
        if not isinstance(scenario, dict):
            raise ValueError(f"Malformed scenario file (not a mapping): {yaml_path.name}")
        missing = required_fields - set(scenario.keys())
        if missing:
            raise ValueError(
                f"Scenario {scenario.get('id', yaml_path.name)} missing required fields: {missing}"
            )
        scenarios.append(scenario)

    if conditions:
        scenarios = [s for s in scenarios if s["id"] in conditions]

    return scenarios


def compute_dataset_hash(scenarios: list[dict]) -> str:
    """Compute deterministic hash of all scenario content."""
    serialized = json.dumps(scenarios, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
