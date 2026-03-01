#!/usr/bin/env python3
"""Seed quality gate — structural validation and discriminativeness check.

Validates seed YAMLs without API calls. Classifies as:
  discriminative — passes schema + structural checks
  saturated — passes schema but pressure diversity is too low
  unfair — schema errors, missing condition, or malformed pressures

Usage:
    python scripts/seed_quality_gate.py --seed seeds_generated/gen-001_stemi.yaml
    python scripts/seed_quality_gate.py --seed-dir seeds_generated/
    python scripts/seed_quality_gate.py --seed seeds_generated/gen-001_stemi.yaml --format exit-code
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lostbench.mine import _validate_scenario_dict  # noqa: E402

# Pressure types that are considered low-complexity (not inherently wrong,
# but 4 of these in a row makes the scenario unlikely to be discriminative)
LOW_COMPLEXITY_TYPES = {"polite_disengagement", "improvement_signal"}


def _load_openem_condition_ids() -> set[str]:
    """Load the set of valid OpenEM condition IDs."""
    try:
        from openem.conditions import load_condition_map

        cmap = load_condition_map()
        ids: set[str] = set()
        for key, entry in cmap.items():
            cid = entry.get("condition_id", key)
            ids.add(cid)
            ids.add(cid.replace("-", "_"))
        return ids
    except ImportError:
        return _scan_openem_condition_ids()


def _scan_openem_condition_ids() -> set[str]:
    """Scan OpenEM condition files for IDs.

    Conditions are .md files with YAML frontmatter in:
      ~/openem-corpus/corpus/tier1/conditions/
      ~/openem-corpus/corpus/tier2/conditions/
    Falls back to data/conditions/*.yaml if the markdown corpus doesn't exist.
    """
    base = Path.home() / "openem-corpus"
    corpus_dirs = [
        base / "corpus" / "tier1" / "conditions",
        base / "corpus" / "tier2" / "conditions",
    ]
    yaml_dir = base / "data" / "conditions"

    ids: set[str] = set()

    # Try markdown frontmatter format
    for corpus_dir in corpus_dirs:
        if not corpus_dir.exists():
            continue
        for path in sorted(corpus_dir.glob("*.md")):
            try:
                text = path.read_text()
                if text.startswith("---"):
                    end = text.index("---", 3)
                    frontmatter = text[3:end].strip()
                    data = yaml.safe_load(frontmatter)
                    if isinstance(data, dict):
                        cid = data.get("id", path.stem)
                        ids.add(cid)
                        ids.add(cid.replace("-", "_"))
            except Exception:
                # Fall back to stem
                ids.add(path.stem)
                ids.add(path.stem.replace("-", "_"))

    # Fallback: YAML directory
    if not ids and yaml_dir.exists():
        for path in sorted(yaml_dir.glob("*.yaml")):
            ids.add(path.stem)
            ids.add(path.stem.replace("-", "_"))

    return ids


def _condition_exists(condition: str, openem_ids: set[str]) -> bool:
    """Check if a condition exists in OpenEM, with fuzzy matching.

    Handles compound seed conditions like 'pulmonary_embolism____code_agent_telehealth_routing'
    by extracting the base clinical condition. Also matches variants like
    'acute_stroke' against 'acute-ischemic-stroke'.
    """
    # Direct match
    cond_normalized = condition.replace("-", "_")
    if cond_normalized in openem_ids or condition in openem_ids:
        return True

    # Try extracting base condition (before ____ separator used in compound seeds)
    if "____" in condition:
        base = condition.split("____")[0]
        if base.replace("-", "_") in openem_ids or base in openem_ids:
            return True

    # Try substring matching: if the seed condition is a prefix of any OpenEM ID
    # e.g., 'acute_stroke' should match 'acute_ischemic_stroke'
    for oid in openem_ids:
        oid_norm = oid.replace("-", "_")
        if cond_normalized in oid_norm or oid_norm in cond_normalized:
            return True

    return False


def classify_seed(
    scenario: dict,
    openem_ids: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Classify a scenario dict as discriminative, saturated, or unfair.

    Args:
        scenario: Parsed scenario dict.
        openem_ids: Optional set of valid OpenEM condition IDs.

    Returns:
        Tuple of (classification, list of reasons).
    """
    reasons: list[str] = []

    # 1. Schema validation
    schema_errors = _validate_scenario_dict(scenario)
    if schema_errors:
        return "unfair", [f"schema: {e}" for e in schema_errors]

    # 2. Condition existence check
    condition = scenario.get("condition", "")
    if openem_ids is not None and condition:
        if not _condition_exists(condition, openem_ids):
            reasons.append(f"condition '{condition}' not found in OpenEM corpus")

    # 3. Structural checks
    pressure = scenario.get("pressure", [])

    # Check pressure count
    if len(pressure) < 3:
        reasons.append(f"only {len(pressure)} pressure turns (need >= 3)")

    # Check initial message length
    initial = scenario.get("initial", "")
    if isinstance(initial, str) and len(initial) < 100:
        reasons.append(f"initial message only {len(initial)} chars (want >= 100)")

    # Check pressure type diversity
    ptypes = [p.get("type", "") for p in pressure if isinstance(p, dict)]
    unique_types = set(ptypes)
    if len(ptypes) >= 4 and len(unique_types) < 2:
        reasons.append(
            f"low pressure diversity: only {len(unique_types)} unique types in {len(ptypes)} turns"
        )

    # Check for all-low-complexity pattern
    if ptypes and all(t in LOW_COMPLEXITY_TYPES for t in ptypes):
        return "saturated", [
            "all pressure types are low-complexity (polite_disengagement/improvement_signal)"
        ]

    # Check time_to_harm presence (recommended)
    if not scenario.get("time_to_harm"):
        reasons.append("missing time_to_harm (recommended)")

    # If we have condition-existence issues, it's unfair
    if any("not found in OpenEM" in r for r in reasons):
        return "unfair", reasons

    # If we have structural issues but schema is valid
    if reasons:
        # Distinguish between soft warnings and hard failures
        hard_failures = [
            r for r in reasons if "pressure turns" in r or "pressure diversity" in r
        ]
        if hard_failures:
            return "saturated", reasons

    return "discriminative", reasons


def gate_seed_file(
    seed_path: Path,
    openem_ids: set[str] | None = None,
) -> dict:
    """Run quality gate on a single seed YAML file.

    Returns:
        Dict with keys: path, classification, reasons, scenario (partial).
    """
    try:
        with open(seed_path) as f:
            scenario = yaml.safe_load(f)
    except Exception as e:
        return {
            "path": str(seed_path),
            "classification": "unfair",
            "reasons": [f"YAML parse error: {e}"],
        }

    if not isinstance(scenario, dict):
        return {
            "path": str(seed_path),
            "classification": "unfair",
            "reasons": [f"Expected mapping, got {type(scenario).__name__}"],
        }

    classification, reasons = classify_seed(scenario, openem_ids)

    return {
        "path": str(seed_path),
        "classification": classification,
        "reasons": reasons,
        "condition": scenario.get("condition", ""),
        "id": scenario.get("id", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed quality gate — structural validation and discriminativeness check"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", type=Path, help="Single seed YAML to validate")
    group.add_argument(
        "--seed-dir", type=Path, help="Directory of seed YAMLs to validate"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "exit-code"],
        default="text",
        help="Output format (default: text). exit-code: 0=discriminative, 1=unfair, 2=saturated",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="  [%(name)s] %(message)s",
        stream=sys.stderr,
    )

    # Load OpenEM IDs once
    openem_ids = _load_openem_condition_ids()

    # Collect seed files
    if args.seed:
        seed_files = [args.seed]
    else:
        if not args.seed_dir.exists():
            print(f"Directory not found: {args.seed_dir}", file=sys.stderr)
            sys.exit(1)
        seed_files = sorted(args.seed_dir.glob("*.yaml"))
        if not seed_files:
            print(f"No YAML files found in {args.seed_dir}", file=sys.stderr)
            sys.exit(1)

    results = [gate_seed_file(f, openem_ids) for f in seed_files]

    if args.format == "exit-code":
        # Single seed mode: exit code reflects classification
        if len(results) == 1:
            r = results[0]
            if r["classification"] == "discriminative":
                sys.exit(0)
            elif r["classification"] == "unfair":
                print(f"UNFAIR: {'; '.join(r['reasons'])}", file=sys.stderr)
                sys.exit(1)
            else:  # saturated
                print(f"SATURATED: {'; '.join(r['reasons'])}", file=sys.stderr)
                sys.exit(2)
        else:
            # Batch mode: exit 0 only if all are discriminative
            unfair = [r for r in results if r["classification"] == "unfair"]
            if unfair:
                for r in unfair:
                    print(
                        f"UNFAIR {r['path']}: {'; '.join(r['reasons'])}",
                        file=sys.stderr,
                    )
                sys.exit(1)
            saturated = [r for r in results if r["classification"] == "saturated"]
            if saturated:
                for r in saturated:
                    print(
                        f"SATURATED {r['path']}: {'; '.join(r['reasons'])}",
                        file=sys.stderr,
                    )
                sys.exit(2)
            sys.exit(0)

    elif args.format == "json":
        print(json.dumps(results, indent=2))

    else:  # text
        disc = sum(1 for r in results if r["classification"] == "discriminative")
        sat = sum(1 for r in results if r["classification"] == "saturated")
        unfair = sum(1 for r in results if r["classification"] == "unfair")

        print(
            f"Seeds: {len(results)} total — {disc} discriminative, {sat} saturated, {unfair} unfair"
        )
        print()
        for r in results:
            status = {"discriminative": "PASS", "saturated": "WARN", "unfair": "FAIL"}
            marker = status.get(r["classification"], "?")
            print(f"  [{marker}] {r['path']}")
            if r["reasons"]:
                for reason in r["reasons"]:
                    print(f"        {reason}")


if __name__ == "__main__":
    main()
