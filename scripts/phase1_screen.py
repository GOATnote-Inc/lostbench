#!/usr/bin/env python3
"""Generate Phase 1 discriminative screen from graded deterministic results.

Reads grade JSONs and identifies seeds that triggered failure in any cell
(model × condition). These are candidates for Phase 2 stochastic eval.

Usage:
    python3 scripts/phase1_screen.py --grades-dir results/seeds-cycle-eval/grades_llm_judge
    python3 scripts/phase1_screen.py --grades-dir results/seeds-cycle-eval/grades_llm_judge --output results/seeds-cycle-eval/phase1_screen.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def generate_screen(grades_dir: Path) -> dict:
    """Scan grade files and classify seeds as discriminative or not."""
    seed_results: dict[str, dict] = defaultdict(
        lambda: {
            "condition": "unknown",
            "cells": {},
            "any_fail": False,
        }
    )

    if not grades_dir.exists():
        print(f"Grades dir not found: {grades_dir}", file=sys.stderr)
        sys.exit(1)

    n_files = 0
    for subdir in sorted(grades_dir.iterdir()):
        if not subdir.is_dir():
            continue
        for grade_file in sorted(subdir.glob("grade_*.json")):
            with open(grade_file) as f:
                grade = json.load(f)
            n_files += 1

            seed_id = grade.get("scenario_id", "unknown")
            model = grade.get("model", "unknown")
            passed = grade.get("pass", False)
            eps = grade.get("eps_point", 0.0)
            condition_name = grade.get("condition", "unknown")

            if "preamble" in subdir.name:
                eval_condition = "preamble_only"
            else:
                eval_condition = "baseline"

            cell_key = f"{model}|{eval_condition}"
            entry = seed_results[seed_id]
            entry["condition"] = condition_name
            entry["cells"][cell_key] = {
                "pass": passed,
                "eps": eps,
                "classA": grade.get("classA", 0),
            }
            if not passed:
                entry["any_fail"] = True

    discriminative = sorted(
        sid for sid, data in seed_results.items() if data["any_fail"]
    )
    non_discriminative = sorted(
        sid for sid, data in seed_results.items() if not data["any_fail"]
    )

    # Failure breakdown by cell
    cell_failures: dict[str, int] = defaultdict(int)
    for sid in discriminative:
        for cell_key, cell_data in seed_results[sid]["cells"].items():
            if not cell_data["pass"]:
                cell_failures[cell_key] += 1

    return {
        "phase": "deterministic_screen",
        "temperature": 0.0,
        "effective_trials": 1,
        "total_graded": len(seed_results),
        "total_grade_files": n_files,
        "discriminative_seeds": discriminative,
        "non_discriminative_seeds": non_discriminative,
        "count_discriminative": len(discriminative),
        "count_non_discriminative": len(non_discriminative),
        "discriminative_rate": round(
            len(discriminative) / max(len(seed_results), 1), 4
        ),
        "cell_failure_counts": dict(sorted(cell_failures.items())),
        "seed_details": {
            sid: {
                "condition": seed_results[sid]["condition"],
                "failed_cells": [
                    k for k, v in seed_results[sid]["cells"].items() if not v["pass"]
                ],
            }
            for sid in discriminative
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate Phase 1 discriminative screen from graded results"
    )
    parser.add_argument(
        "--grades-dir",
        type=Path,
        required=True,
        help="Directory containing grade subdirectories",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for phase1_screen.json (default: parent of grades-dir)",
    )
    args = parser.parse_args()

    screen = generate_screen(args.grades_dir)

    output = args.output or args.grades_dir.parent / "phase1_screen.json"
    with open(output, "w") as f:
        json.dump(screen, f, indent=2)

    print("Phase 1 Discriminative Screen (temp=0, n=1 effective)")
    print(f"  Grade files scanned: {screen['total_grade_files']}")
    print(f"  Seeds graded: {screen['total_graded']}")
    print(
        f"  Discriminative (triggered failure): "
        f"{screen['count_discriminative']} ({screen['discriminative_rate']:.0%})"
    )
    print(f"  Non-discriminative (always passed): {screen['count_non_discriminative']}")
    print(f"  Phase 2 candidates: {screen['count_discriminative']} seeds")
    print()
    print("  Cell failure counts:")
    for cell, count in screen["cell_failure_counts"].items():
        print(f"    {cell}: {count}")
    print(f"\n  Wrote: {output}")


if __name__ == "__main__":
    main()
