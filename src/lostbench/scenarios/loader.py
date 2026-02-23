"""Scenario loader for LostBench."""

import hashlib
import json

import yaml

from lostbench.config import SCENARIOS_DIR

VALID_CEIS_SUITES = {"capability", "regression"}

# Holdback scenarios are excluded from public releases to enable
# contamination detection. A clean model shows similar pass rates on
# published and holdback sets. A contaminated model performs significantly
# better on published scenarios.
#
# Selection criteria: medium-difficulty, diverse specialties, not the
# most commonly discussed emergency conditions.
HOLDBACK_SCENARIOS: set[str] = {
    "MTR-003",  # testicular_torsion (urology)
    "MTR-007",  # crao_stroke (ophthalmology)
    "MTR-013",  # septic_arthritis (rheumatology/ortho)
    "MTR-016",  # tension_pneumothorax (trauma)
    "MTR-020",  # cauda_equina (neuro/ortho)
    "MTR-023",  # acute_limb_ischemia (vascular)
}

# CI subset: 8 diverse published scenarios for quick regression checks.
# Covers pediatric, metabolic, neuro, OB/GYN, cardiac, psychiatric,
# and surgical specialties.
CI_SCENARIOS: list[str] = [
    "MTR-001",  # neonatal_sepsis
    "MTR-004",  # dka
    "MTR-006",  # sah
    "MTR-009",  # ectopic_pregnancy
    "MTR-012",  # acute_ischemic_stroke
    "MTR-015",  # aortic_dissection
    "MTR-018",  # suicidal_ideation_plan_means
    "MTR-022",  # kawasaki_disease
]

# CI subset for new adversarial expansion corpora (2 per category)
CI_ADVERSARIAL_EXPANSION: list[str] = [
    "TUE-001",  # tool-use: stemi
    "TUE-003",  # tool-use: pulmonary_embolism
    "CAM-001",  # code-agent: stemi
    "CAM-005",  # code-agent: suicidal_ideation
    "MMV-001",  # multimodal: stemi
    "MMV-003",  # multimodal: meningococcemia
    "PRI-001",  # integrated: stemi
    "PRI-006",  # integrated: acute_ischemic_stroke
]


def _validate_ceis_block(scenario_id: str, ceis: dict) -> None:
    """Validate optional CEIS metadata block. Raises ValueError on invalid data."""
    if not isinstance(ceis, dict):
        raise ValueError(
            f"{scenario_id}: ceis block must be a mapping, got {type(ceis).__name__}"
        )

    if "severity_weight" in ceis:
        sw = ceis["severity_weight"]
        if not isinstance(sw, (int, float)):
            raise ValueError(
                f"{scenario_id}: ceis.severity_weight must be numeric, got {type(sw).__name__}"
            )
        if not (0.0 <= sw <= 2.0):
            raise ValueError(
                f"{scenario_id}: ceis.severity_weight must be in [0.0, 2.0], got {sw}"
            )

    if "required_escalation_level" in ceis:
        rel = ceis["required_escalation_level"]
        if not isinstance(rel, int):
            raise ValueError(
                f"{scenario_id}: ceis.required_escalation_level must be int, got {type(rel).__name__}"
            )
        if rel not in (0, 1, 2, 3):
            raise ValueError(
                f"{scenario_id}: ceis.required_escalation_level must be 0-3, got {rel}"
            )

    if "suite" in ceis:
        suite = ceis["suite"]
        if suite not in VALID_CEIS_SUITES:
            raise ValueError(
                f"{scenario_id}: ceis.suite must be one of {VALID_CEIS_SUITES}, got {suite!r}"
            )


def load_scenarios(
    corpus: str = "emergency",
    conditions: list[str] | None = None,
    partition: str | None = None,
) -> list[dict]:
    """Load scenario YAML files for a given corpus.

    Args:
        corpus: Which corpus to load (emergency, crisis-resource, defer).
        conditions: Optional list of scenario IDs to filter to.
        partition: Optional partition filter:
            - "published": exclude holdback scenarios (default for public use)
            - "holdback": only holdback scenarios
            - "all" or None: include everything (default, backward-compatible)
    """
    required_fields = {"id", "condition", "initial"}

    if corpus == "emergency":
        scenario_dir = SCENARIOS_DIR / "tier1"
    elif corpus == "adversarial":
        scenario_dir = SCENARIOS_DIR / "tier1_adversarial"
    elif corpus == "crisis-resource":
        scenario_dir = SCENARIOS_DIR / "tier1_crisis"
    elif corpus == "defer":
        scenario_dir = SCENARIOS_DIR / "defer"
    elif corpus == "tool-use":
        scenario_dir = SCENARIOS_DIR / "tier1_tooluse"
    elif corpus == "code-agent":
        scenario_dir = SCENARIOS_DIR / "tier1_codeagent"
    elif corpus == "multimodal":
        scenario_dir = SCENARIOS_DIR / "tier1_multimodal"
    elif corpus == "integrated":
        scenario_dir = SCENARIOS_DIR / "tier1_integrated"
    elif corpus == "adversarial-all":
        # Load all adversarial subdirs combined
        all_scenarios: list[dict] = []
        for subdir in [
            "tier1_adversarial",
            "tier1_tooluse",
            "tier1_codeagent",
            "tier1_multimodal",
            "tier1_integrated",
        ]:
            dir_path = SCENARIOS_DIR / subdir
            if not dir_path.exists():
                continue
            for yaml_path in sorted(dir_path.glob("*.yaml")):
                with open(yaml_path) as f:
                    scenario = yaml.safe_load(f)
                if not isinstance(scenario, dict):
                    raise ValueError(
                        f"Malformed scenario file (not a mapping): {yaml_path.name}"
                    )
                missing = required_fields - set(scenario.keys())
                if missing:
                    raise ValueError(
                        f"Scenario {scenario.get('id', yaml_path.name)} missing required fields: {missing}"
                    )
                if "ceis" in scenario:
                    _validate_ceis_block(scenario["id"], scenario["ceis"])
                all_scenarios.append(scenario)
        if conditions:
            all_scenarios = [s for s in all_scenarios if s["id"] in conditions]
        return all_scenarios
    else:
        raise ValueError(f"Unknown corpus: {corpus}")
    scenarios = []
    for yaml_path in sorted(scenario_dir.glob("*.yaml")):
        with open(yaml_path) as f:
            scenario = yaml.safe_load(f)
        if not isinstance(scenario, dict):
            raise ValueError(
                f"Malformed scenario file (not a mapping): {yaml_path.name}"
            )
        missing = required_fields - set(scenario.keys())
        if missing:
            raise ValueError(
                f"Scenario {scenario.get('id', yaml_path.name)} missing required fields: {missing}"
            )
        if "ceis" in scenario:
            _validate_ceis_block(scenario["id"], scenario["ceis"])
        scenarios.append(scenario)

    # Apply partition filter (only affects emergency corpus)
    if partition and partition != "all" and corpus == "emergency":
        if partition == "published":
            scenarios = [s for s in scenarios if s["id"] not in HOLDBACK_SCENARIOS]
        elif partition == "holdback":
            scenarios = [s for s in scenarios if s["id"] in HOLDBACK_SCENARIOS]
        else:
            raise ValueError(
                f"Unknown partition: {partition!r} (expected 'published', 'holdback', or 'all')"
            )

    if conditions:
        scenarios = [s for s in scenarios if s["id"] in conditions]

    return scenarios


def compute_dataset_hash(scenarios: list[dict]) -> str:
    """Compute deterministic hash of all scenario content."""
    serialized = json.dumps(scenarios, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()
