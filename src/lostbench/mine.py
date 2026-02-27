"""Mine — Seed JSON to LostBench YAML conversion + hypothesis-driven generation.

Two modes:
  (a) Convert existing ScribeGoat2 seed JSON to LostBench YAML
  (b) Generate new scenarios from a failure hypothesis (v1: stub)

Maps pressure operator codes (SI, CD, PEN, AC, FB, etc.) to LostBench pressure types.
Validates schema and clinical plausibility.

Usage:
    from lostbench.mine import convert_seed, validate_scenario_yaml
    scenario = convert_seed(seed_json, output_dir="./mined")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ScribeGoat2 pressure operator codes -> LostBench pressure types
OPERATOR_MAP: dict[str, str] = {
    "SI": "improvement_signal",
    "CD": "polite_disengagement",
    "PEN": "rational_framing",
    "AC": "autonomy_assertion",
    "FB": "financial_barrier",
    "SP": "social_pressure",
    "AT": "authority_trust",
    "PT": "provider_trust",
    "SD": "system_distrust",
    "PE": "prior_experience",
    "RF": "rational_framing",
    "AA": "autonomy_assertion",
}

# Required fields for a valid LostBench scenario
REQUIRED_FIELDS = {"id", "condition", "initial", "corpus"}

# Valid corpus types
VALID_CORPORA = {
    "emergency",
    "crisis-resource",
    "defer",
    "adversarial",
    "tool-use",
    "code-agent",
    "multimodal",
    "integrated",
}

# Valid pressure types
VALID_PRESSURE_TYPES = {
    "financial_barrier",
    "social_pressure",
    "autonomy_assertion",
    "polite_disengagement",
    "improvement_signal",
    "rational_framing",
    "authority_trust",
    "provider_trust",
    "system_distrust",
    "prior_experience",
}


# ScribeGoat2 full-name pressure operators -> LostBench pressure types
PRESSURE_NAME_MAP: dict[str, str] = {
    "minimization": "improvement_signal",
    "cost_barrier": "financial_barrier",
    "self_diagnosis": "rational_framing",
    "authority_challenge": "authority_trust",
    "improvement_signal": "improvement_signal",
    "autonomy_assertion": "autonomy_assertion",
    "social_pressure": "social_pressure",
    "financial_barrier": "financial_barrier",
    "polite_disengagement": "polite_disengagement",
    "rational_framing": "rational_framing",
    "authority_trust": "authority_trust",
    "provider_trust": "provider_trust",
    "system_distrust": "system_distrust",
    "prior_experience": "prior_experience",
}


def _map_pressure_type(operator_code: str) -> str:
    """Map ScribeGoat2 operator code or name to LostBench pressure type."""
    # Try full name first (ScribeGoat2 turns format)
    name_match = PRESSURE_NAME_MAP.get(operator_code.lower())
    if name_match:
        return name_match
    # Try operator code (ScribeGoat2 seed format)
    return OPERATOR_MAP.get(operator_code.upper(), "rational_framing")


def _generate_scenario_id(seed_id: str, condition: str) -> str:
    """Generate a LostBench-style scenario ID from seed info."""
    # Extract numeric part from SEED-NNN
    num = seed_id.replace("SEED-", "").replace("seed-", "")
    try:
        num_int = int(num)
    except ValueError:
        num_int = 999
    return f"SEED-{num_int:03d}"


def convert_seed(
    seed_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict:
    """Convert a ScribeGoat2 seed JSON to LostBench scenario YAML.

    Args:
        seed_path: Path to a seed JSON file.
        output_dir: Where to write the YAML. If None, returns dict without writing.

    Returns:
        The converted scenario dict.
    """
    seed_path = Path(seed_path)
    with open(seed_path) as f:
        seed = json.load(f)

    # Extract fields from seed
    seed_id = seed.get(
        "seed_id", seed.get("scenario_id", seed.get("id", seed_path.stem))
    )
    condition = seed.get("condition", "unknown")
    # Normalize: "STEMI (ST-Elevation Myocardial Infarction)" -> "stemi"
    # Take text before first paren, then snake_case
    if "(" in condition:
        condition = condition[: condition.index("(")].strip()
    condition_snake = condition.lower().replace(" ", "_").replace("-", "_")

    # Build initial message and pressure turns
    # Handle two seed formats:
    #   Format A (ScribeGoat2 full): turns[] with user_prompt + pressure_operators
    #   Format B (simple): initial_message/initial + pressure_turns/pressure
    turns = seed.get("turns", [])
    if turns:
        # Format A: extract initial from turn 1, pressure from turns 2+
        initial = turns[0].get("user_prompt", "") if turns else ""
        pressure_turns = []
        for t in turns[1:]:
            operators = t.get("pressure_operators", [])
            # Map first operator code to pressure type
            op_code = operators[0] if operators else "RF"
            pressure_turns.append(
                {
                    "type": _map_pressure_type(op_code),
                    "turn": t.get("turn_number", len(pressure_turns) + 2),
                    "content": t.get("user_prompt", ""),
                }
            )
    else:
        # Format B: simple fields
        initial = seed.get("initial_message", seed.get("initial", ""))
        if not initial:
            presentation = seed.get("presentation", "")
            if presentation:
                initial = presentation

        pressure_turns = []
        raw_pressures = seed.get("pressure_turns", seed.get("pressure", []))
        for i, p in enumerate(raw_pressures):
            if isinstance(p, str):
                pressure_turns.append(
                    {
                        "type": "rational_framing",
                        "turn": i + 2,
                        "content": p,
                    }
                )
            elif isinstance(p, dict):
                operator = p.get("operator", p.get("type", "RF"))
                content = p.get("content", p.get("message", ""))
                pressure_turns.append(
                    {
                        "type": _map_pressure_type(operator),
                        "turn": p.get("turn", i + 2),
                        "content": content,
                    }
                )

    # Determine corpus type
    corpus = seed.get("corpus", "emergency")
    attack_family = seed.get("attack_family", seed.get("vector", ""))
    if attack_family:
        family_lower = attack_family.lower().replace(" ", "-").replace("_", "-")
        if "code" in family_lower:
            corpus = "code-agent"
        elif "tool" in family_lower:
            corpus = "tool-use"
        elif "multimodal" in family_lower:
            corpus = "multimodal"
        elif "integrated" in family_lower:
            corpus = "integrated"
        elif "adversarial" in family_lower:
            corpus = "adversarial"

    # Build scenario
    scenario_id = _generate_scenario_id(seed_id, condition_snake)
    scenario: dict = {
        "id": scenario_id,
        "condition": condition_snake,
        "corpus": corpus,
        "initial": initial,
        "pressure": pressure_turns,
    }

    # Optional CEIS metadata
    severity_weight = seed.get("severity_weight", seed.get("severity", None))
    if severity_weight is not None:
        scenario["ceis"] = {
            "severity_weight": float(severity_weight),
            "required_escalation_level": seed.get("required_escalation_level", 3),
            "suite": "capability",
        }

    # Optional time_to_harm (ScribeGoat2 uses time_to_harm_hours)
    tth = seed.get("time_to_harm", seed.get("time_to_harm_hours", ""))
    if tth:
        scenario["time_to_harm"] = tth

    # Optional metadata
    if attack_family:
        scenario["attack_family"] = attack_family
    source = seed.get("source", "")
    if source:
        scenario["source"] = source

    # Write if output_dir provided
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{scenario_id.lower()}_{condition_snake}.yaml"
        out_path = output_dir / filename
        with open(out_path, "w") as f:
            yaml.dump(scenario, f, default_flow_style=False, sort_keys=False)
        logger.info("Converted %s -> %s", seed_path.name, out_path)

    return scenario


def convert_seed_dir(
    seed_dir: str | Path,
    output_dir: str | Path,
) -> list[dict]:
    """Batch-convert all seed JSONs in a directory.

    Args:
        seed_dir: Directory containing seed JSON files.
        output_dir: Where to write converted YAMLs.

    Returns:
        List of converted scenario dicts.
    """
    seed_dir = Path(seed_dir)
    results = []
    for path in sorted(seed_dir.glob("*.json")):
        try:
            scenario = convert_seed(path, output_dir)
            results.append(scenario)
        except Exception as e:
            logger.error("Failed to convert %s: %s", path.name, e)
    logger.info("Converted %d seeds -> %s", len(results), output_dir)
    return results


def validate_scenario_yaml(
    path: str | Path,
) -> list[str]:
    """Validate a scenario YAML against LostBench schema.

    Args:
        path: Path to a YAML scenario file.

    Returns:
        List of validation error messages (empty if valid).
    """
    path = Path(path)
    errors: list[str] = []

    try:
        with open(path) as f:
            scenario = yaml.safe_load(f)
    except Exception as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(scenario, dict):
        return [f"Expected mapping, got {type(scenario).__name__}"]

    # Required fields
    missing = REQUIRED_FIELDS - set(scenario.keys())
    if missing:
        errors.append(f"Missing required fields: {missing}")

    # Validate corpus
    corpus = scenario.get("corpus", "")
    if corpus and corpus not in VALID_CORPORA:
        errors.append(f"Invalid corpus: {corpus!r}")

    # Validate pressure turns
    pressure = scenario.get("pressure", [])
    if not isinstance(pressure, list):
        errors.append("pressure must be a list")
    else:
        for i, p in enumerate(pressure):
            if not isinstance(p, dict):
                errors.append(f"pressure[{i}] must be a mapping")
                continue
            if "content" not in p:
                errors.append(f"pressure[{i}] missing 'content'")
            ptype = p.get("type", "")
            if ptype and ptype not in VALID_PRESSURE_TYPES:
                errors.append(f"pressure[{i}] invalid type: {ptype!r}")

    # Validate CEIS block
    ceis = scenario.get("ceis")
    if ceis is not None:
        if not isinstance(ceis, dict):
            errors.append("ceis must be a mapping")
        else:
            sw = ceis.get("severity_weight")
            if sw is not None:
                if not isinstance(sw, (int, float)):
                    errors.append("ceis.severity_weight must be numeric")
                elif not (0.0 <= sw <= 2.0):
                    errors.append(f"ceis.severity_weight out of range: {sw}")

            rel = ceis.get("required_escalation_level")
            if rel is not None:
                if not isinstance(rel, int) or rel not in (0, 1, 2, 3):
                    errors.append(f"ceis.required_escalation_level invalid: {rel}")

    # Clinical plausibility: initial message should be non-trivial
    initial = scenario.get("initial", "")
    if isinstance(initial, str) and len(initial) < 20:
        errors.append("initial message too short (< 20 chars)")

    return errors


def generate_from_hypothesis(
    hypothesis: str,
    failure_class: str | None = None,
    clinical_domain: str | None = None,
    count: int = 1,
    output_dir: str | Path | None = None,
) -> list[dict]:
    """Generate scenarios from a failure hypothesis.

    v1: Stub that returns empty list with informational message.
    Wired for future LLM-powered generation.

    Args:
        hypothesis: Natural language failure hypothesis.
        failure_class: Optional target failure class (A/B/C/D).
        clinical_domain: Optional target clinical domain.
        count: Number of scenarios to generate.
        output_dir: Where to write generated YAMLs.

    Returns:
        Empty list (v1 stub).
    """
    logger.info(
        "LLM generation not yet implemented — use --seed-dir for format conversion"
    )
    logger.info("Hypothesis: %s", hypothesis)
    if failure_class:
        logger.info("Target failure class: %s", failure_class)
    if clinical_domain:
        logger.info("Target clinical domain: %s", clinical_domain)
    return []
