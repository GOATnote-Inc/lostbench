#!/usr/bin/env python3
"""Consolidate cycle-generated seeds into a flat directory with unique IDs.

Each coverage cycle numbers seeds independently (GEN-001, GEN-002, ...),
creating ID collisions across cycles. This script assigns unique CYC-NNN IDs
and writes consolidated copies to a single directory for evaluation.

Usage:
    python3 scripts/consolidate_cycle_seeds.py --output-dir seeds_generated/eval_batch
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def discover_cycle_seeds(base_dir: Path) -> list[tuple[Path, str]]:
    """Find all gen-*.yaml files across cycle_* directories.

    Returns list of (path, cycle_name) sorted by cycle then filename.
    """
    seeds = []
    for cycle_dir in sorted(base_dir.glob("cycle_*")):
        if not cycle_dir.is_dir():
            continue
        for seed_path in sorted(cycle_dir.glob("gen-*.yaml")):
            seeds.append((seed_path, cycle_dir.name))
    return seeds


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate cycle seeds with unique CYC-NNN IDs"
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).parent.parent / "seeds_generated",
        help="Base directory containing cycle_* subdirectories",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for consolidated seeds",
    )
    args = parser.parse_args()

    seeds = discover_cycle_seeds(args.base_dir)
    if not seeds:
        print(
            f"No cycle seeds found in {args.base_dir}/cycle_*/gen-*.yaml",
            file=sys.stderr,
        )
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {}
    for i, (seed_path, cycle_name) in enumerate(seeds, start=1):
        new_id = f"CYC-{i:03d}"

        with open(seed_path) as f:
            data = yaml.safe_load(f)

        original_id = data.get("id", "unknown")
        condition = data.get("condition", "unknown")

        # Assign unique ID and preserve source traceability
        data["id"] = new_id
        data["_source"] = {
            "original_id": original_id,
            "cycle": cycle_name,
            "original_path": str(seed_path.relative_to(args.base_dir)),
        }

        # Write consolidated seed
        filename = f"cyc-{i:03d}_{condition}.yaml"
        out_path = args.output_dir / filename
        with open(out_path, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=120,
            )

        manifest[new_id] = {
            "original_id": original_id,
            "cycle": cycle_name,
            "condition": condition,
            "original_path": str(seed_path.relative_to(args.base_dir)),
            "consolidated_file": filename,
        }

    # Write manifest
    manifest_path = args.output_dir / "_consolidation_manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(
            manifest,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )

    print(f"Consolidated {len(seeds)} seeds → {args.output_dir}")
    print(f"IDs: CYC-001 through CYC-{len(seeds):03d}")
    print(f"Manifest: {manifest_path}")

    # Per-cycle breakdown
    from collections import Counter

    cycle_counts = Counter(cycle_name for _, cycle_name in seeds)
    for cycle, count in sorted(cycle_counts.items()):
        print(f"  {cycle}: {count} seeds")


if __name__ == "__main__":
    main()
