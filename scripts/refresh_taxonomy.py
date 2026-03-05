#!/usr/bin/env python3
"""Attack Taxonomy Refresh from mining results.

Additive only: extends pressure type lists, adds new exploit families,
adds trajectory archetype annotations. Never removes existing entries.

Usage:
    python3 scripts/refresh_taxonomy.py                # dry-run (default)
    python3 scripts/refresh_taxonomy.py --apply         # write changes
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = REPO_ROOT / "configs" / "attack_taxonomy.yaml"
ANALYSIS_DIR = REPO_ROOT / "results" / "analysis"
PROPOSED_FAMILIES_PATH = ANALYSIS_DIR / "proposed_families.yaml"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _bump_version(version: str) -> str:
    """Bump patch version: 1.0.0 -> 1.1.0."""
    parts = version.split(".")
    if len(parts) == 3:
        parts[1] = str(int(parts[1]) + 1)
        parts[2] = "0"
    return ".".join(parts)


def refresh_pressure_types(
    taxonomy: dict,
    pressure: dict,
    min_observations: int = 50,
) -> list[str]:
    """Add mined pressure types to taxonomy pressure_taxonomy list."""
    existing_types = set()
    for item in taxonomy.get("pressure_taxonomy", []):
        if isinstance(item, str):
            existing_types.add(item)
        elif isinstance(item, dict):
            existing_types.add(item.get("type", ""))

    new_types = []
    # Collect all pressure types across all models
    all_types: dict[str, int] = {}
    for model_data in pressure.values():
        if not isinstance(model_data, dict):
            continue
        for ptype, stats in model_data.items():
            if not isinstance(stats, dict):
                continue
            total = stats.get("total", 0)
            all_types[ptype] = all_types.get(ptype, 0) + total

    for ptype, total in sorted(all_types.items(), key=lambda x: -x[1]):
        if ptype not in existing_types and total >= min_observations:
            new_types.append(ptype)

    return new_types


def refresh_exploit_families(
    taxonomy: dict,
    proposed_families: dict,
) -> list[dict]:
    """Add proposed families to taxonomy vectors."""
    existing_ids = set()
    for vector in taxonomy.get("vectors", []):
        for fam_id in vector.get("exploit_families", []):
            existing_ids.add(fam_id)

    new_families = []
    for fam in proposed_families.get("proposed_families", []):
        fid = fam.get("family_id", "")
        if fid and fid not in existing_ids:
            new_families.append(fam)

    return new_families


def refresh_archetypes(
    taxonomy: dict,
    trajectory: dict,
) -> dict[str, str]:
    """Add trajectory archetype annotations."""
    archetype_dist = trajectory.get("archetype_distribution", {})
    annotations = {}
    for arch, count in archetype_dist.items():
        if arch != "ungraded" and count > 0:
            annotations[arch] = count
    return annotations


def apply_refresh(
    taxonomy: dict,
    new_pressure_types: list[str],
    new_families: list[dict],
    archetype_annotations: dict,
) -> dict:
    """Apply all additive changes to taxonomy."""
    # Add pressure types
    if new_pressure_types:
        if "pressure_taxonomy" not in taxonomy:
            taxonomy["pressure_taxonomy"] = []
        for pt in new_pressure_types:
            taxonomy["pressure_taxonomy"].append(pt)

    # Add exploit families to adversarial vector
    if new_families:
        for vector in taxonomy.get("vectors", []):
            if vector.get("id") == "adversarial":
                for fam in new_families:
                    fid = fam.get("family_id", "")
                    if fid not in vector.get("exploit_families", []):
                        vector.setdefault("exploit_families", []).append(fid)
                break

    # Add archetype annotations
    if archetype_annotations:
        taxonomy["trajectory_archetypes"] = archetype_annotations

    # Bump version
    taxonomy["version"] = _bump_version(taxonomy.get("version", "1.0.0"))
    taxonomy["last_modified"] = date.today().isoformat()

    return taxonomy


def render_diff(
    new_pressure_types: list[str],
    new_families: list[dict],
    archetype_annotations: dict,
    new_version: str,
) -> str:
    """Render proposed changes as diff report."""
    lines = [
        "# Taxonomy Refresh Report",
        "",
        f"Generated: {date.today().isoformat()}",
        f"New version: {new_version}",
        "",
    ]

    if new_pressure_types:
        lines.append(f"## New Pressure Types ({len(new_pressure_types)})")
        lines.append("")
        for pt in new_pressure_types:
            lines.append(f"+ {pt}")
        lines.append("")

    if new_families:
        lines.append(f"## New Exploit Families ({len(new_families)})")
        lines.append("")
        for fam in new_families:
            lines.append(f"+ {fam.get('family_id', '')} ({fam.get('name', '')})")
        lines.append("")

    if archetype_annotations:
        lines.append(f"## Trajectory Archetypes ({len(archetype_annotations)})")
        lines.append("")
        for arch, count in sorted(archetype_annotations.items(), key=lambda x: -x[1]):
            lines.append(f"+ {arch}: {count}")
        lines.append("")

    if not new_pressure_types and not new_families and not archetype_annotations:
        lines.append("No changes to propose. Taxonomy is current.")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Refresh attack_taxonomy.yaml from mining results (additive only)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default: dry-run diff only)",
    )
    parser.add_argument(
        "--taxonomy",
        default=str(TAXONOMY_PATH),
        help="Path to attack_taxonomy.yaml",
    )
    args = parser.parse_args()

    taxonomy_path = Path(args.taxonomy)
    taxonomy = load_yaml(taxonomy_path)
    original_version = taxonomy.get("version", "1.0.0")

    # Load mining analysis
    pressure = load_json(ANALYSIS_DIR / "pressure_effectiveness.json")
    trajectory = load_json(ANALYSIS_DIR / "trajectory_analysis.json")
    proposed_families = load_yaml(PROPOSED_FAMILIES_PATH)

    new_pressure_types = []
    if pressure:
        new_pressure_types = refresh_pressure_types(taxonomy, pressure)

    new_families = []
    if proposed_families:
        new_families = refresh_exploit_families(taxonomy, proposed_families)

    archetype_annotations = {}
    if trajectory:
        archetype_annotations = refresh_archetypes(taxonomy, trajectory)

    new_version = _bump_version(original_version)

    # Show diff
    report = render_diff(
        new_pressure_types, new_families, archetype_annotations, new_version
    )
    print(report)

    total_changes = (
        len(new_pressure_types) + len(new_families) + len(archetype_annotations)
    )
    print(f"Total changes: {total_changes}", file=sys.stderr)

    if args.apply and total_changes > 0:
        taxonomy = apply_refresh(
            taxonomy, new_pressure_types, new_families, archetype_annotations
        )
        with open(taxonomy_path, "w") as f:
            yaml.dump(taxonomy, f, default_flow_style=False, sort_keys=False)
        print(f"Taxonomy updated: {taxonomy_path} (v{new_version})", file=sys.stderr)

        # Validate output
        with open(taxonomy_path) as f:
            validated = yaml.safe_load(f)
        if validated:
            print("Validation: YAML parses successfully", file=sys.stderr)
        else:
            print("WARNING: Validation failed — empty YAML", file=sys.stderr)
    elif args.apply:
        print("No changes to apply", file=sys.stderr)


if __name__ == "__main__":
    main()
