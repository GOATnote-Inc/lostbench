#!/usr/bin/env python3
"""Generate per-lab safety briefs from LostBench campaign results.

Reads existing artifacts (no API calls, no model inference) and produces
markdown briefs for each frontier lab's safety team.

Usage:
    python3 scripts/generate_safety_briefs.py
    python3 scripts/generate_safety_briefs.py --lab anthropic
    python3 scripts/generate_safety_briefs.py --output-dir reports/safety-briefs
    python3 scripts/generate_safety_briefs.py --results-dir results/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lostbench.safety_briefs import LAB_MODELS, generate_all_briefs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate per-lab safety briefs from LostBench results."
    )
    parser.add_argument(
        "--lab",
        choices=list(LAB_MODELS.keys()),
        default=None,
        help="Generate brief for a single lab only.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "safety-briefs",
        help="Output directory for briefs (default: reports/safety-briefs/).",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=REPO_ROOT / "results",
        help="Results directory to read from (default: results/).",
    )
    parser.add_argument(
        "--no-comparison",
        action="store_true",
        help="Skip cross-lab comparison generation.",
    )
    args = parser.parse_args()

    if not args.results_dir.exists():
        print(
            f"Error: results directory not found: {args.results_dir}", file=sys.stderr
        )
        sys.exit(1)

    index_path = args.results_dir / "index.yaml"
    if not index_path.exists():
        print(f"Error: index.yaml not found at {index_path}", file=sys.stderr)
        sys.exit(1)

    metadata = generate_all_briefs(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        lab_filter=args.lab,
        skip_comparison=args.no_comparison,
    )

    print(f"Generated {len(metadata['generated_files'])} files in {args.output_dir}/")
    for f in metadata["generated_files"]:
        print(f"  {f}")
    print(f"Experiments: {metadata['n_experiments']}")
    print(f"CEIS results: {metadata['n_ceis_results']}")
    print(f"Index SHA-256: {metadata['index_sha256'][:16]}...")


if __name__ == "__main__":
    main()
