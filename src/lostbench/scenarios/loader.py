"""Scenario loader for LostBench."""

import hashlib
import json

import yaml

from lostbench.config import SCENARIOS_DIR

VALID_CEIS_SUITES = {"capability", "regression"}


def _validate_ceis_block(scenario_id: str, ceis: dict) -> None:
    """Validate optional CEIS metadata block. Raises ValueError on invalid data."""
    if not isinstance(ceis, dict):
        raise ValueError(f"{scenario_id}: ceis block must be a mapping, got {type(ceis).__name__}")

    if "severity_weight" in ceis:
        sw = ceis["severity_weight"]
        if not isinstance(sw, (int, float)):
            raise ValueError(f"{scenario_id}: ceis.severity_weight must be numeric, got {type(sw).__name__}")
        if not (0.0 <= sw <= 2.0):
            raise ValueError(f"{scenario_id}: ceis.severity_weight must be in [0.0, 2.0], got {sw}")

    if "required_escalation_level" in ceis:
        rel = ceis["required_escalation_level"]
        if not isinstance(rel, int):
            raise ValueError(f"{scenario_id}: ceis.required_escalation_level must be int, got {type(rel).__name__}")
        if rel not in (0, 1, 2, 3):
            raise ValueError(f"{scenario_id}: ceis.required_escalation_level must be 0-3, got {rel}")

    if "suite" in ceis:
        suite = ceis["suite"]
        if suite not in VALID_CEIS_SUITES:
            raise ValueError(f"{scenario_id}: ceis.suite must be one of {VALID_CEIS_SUITES}, got {suite!r}")


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
        if "ceis" in scenario:
            _validate_ceis_block(scenario["id"], scenario["ceis"])
        scenarios.append(scenario)

    if conditions:
        scenarios = [s for s in scenarios if s["id"] in conditions]

    return scenarios


def compute_dataset_hash(scenarios: list[dict]) -> str:
    """Compute deterministic hash of all scenario content."""
    serialized = json.dumps(scenarios, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
