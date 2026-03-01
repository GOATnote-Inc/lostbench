#!/usr/bin/env python3
"""Coverage report — maps OpenEM conditions to LostBench scenario coverage.

Produces a priority-ranked report of uncovered and undertested conditions.
Output feeds into miners and hooks for the seed mining pipeline.

Usage:
    python scripts/coverage_report.py --format text
    python scripts/coverage_report.py --format json --cache
    python scripts/coverage_report.py --format summary
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

# Scenario corpus directories (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
SCENARIO_DIRS = [
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "tier1",
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "tier1_adversarial",
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "tier1_crisis",
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "defer",
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "tier1_tooluse",
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "tier1_codeagent",
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "tier1_multimodal",
    REPO_ROOT / "src" / "lostbench" / "scenarios" / "tier1_integrated",
]
SEEDS_MINED_DIR = REPO_ROOT / "seeds_mined"
SEEDS_GENERATED_DIR = REPO_ROOT / "seeds_generated"
CACHE_PATH = REPO_ROOT / ".coverage_cache.json"


def _load_openem_conditions() -> list[dict]:
    """Load OpenEM conditions with metadata."""
    try:
        from openem.conditions import load_condition_map

        cmap = load_condition_map()
        seen: set[str] = set()
        conditions = []
        for key, entry in cmap.items():
            cid = entry.get("condition_id", key)
            if cid not in seen:
                seen.add(cid)
                conditions.append(entry)
        return conditions
    except ImportError:
        logger.info("openem not installed — falling back to corpus directory scan")
        return _scan_openem_conditions()


def _scan_openem_conditions() -> list[dict]:
    """Scan OpenEM condition files directly from disk.

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
    # Fallback to older layout
    yaml_dir = base / "data" / "conditions"

    found_any = False
    conditions = []

    # Try markdown frontmatter format first
    for corpus_dir in corpus_dirs:
        if not corpus_dir.exists():
            continue
        found_any = True
        for path in sorted(corpus_dir.glob("*.md")):
            try:
                text = path.read_text()
                if not text.startswith("---"):
                    continue
                # Extract YAML frontmatter between --- markers
                end = text.index("---", 3)
                frontmatter = text[3:end].strip()
                data = yaml.safe_load(frontmatter)
                if isinstance(data, dict):
                    data.setdefault("condition_id", data.get("id", path.stem))
                    # Normalize category field name
                    if "category" in data and "abem_category" not in data:
                        data["abem_category"] = data["category"]
                    conditions.append(data)
            except Exception as e:
                logger.warning("Failed to load %s: %s", path.name, e)

    # Fallback: try YAML directory
    if not found_any and yaml_dir.exists():
        for path in sorted(yaml_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    data.setdefault("condition_id", path.stem)
                    conditions.append(data)
            except Exception as e:
                logger.warning("Failed to load %s: %s", path.name, e)

    if not conditions:
        logger.error("OpenEM corpus not found at %s", base)

    return conditions


def _load_covered_conditions() -> dict[str, str]:
    """Load condition IDs from all scenario and seed directories.

    Returns:
        Dict mapping condition_id -> coverage_source ("scenario" or "seed").
    """
    covered: dict[str, str] = {}

    # Scenarios
    for scenario_dir in SCENARIO_DIRS:
        if not scenario_dir.exists():
            continue
        for path in scenario_dir.glob("*.yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and "condition" in data:
                    cond = data["condition"]
                    covered[cond] = "covered_scenario"
            except Exception:
                continue

    # Seeds (mined)
    if SEEDS_MINED_DIR.exists():
        for path in SEEDS_MINED_DIR.glob("*.yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and "condition" in data:
                    cond = data["condition"]
                    if cond not in covered:
                        covered[cond] = "covered_seed"
            except Exception:
                continue

    # Seeds (generated)
    if SEEDS_GENERATED_DIR.exists():
        for path in SEEDS_GENERATED_DIR.glob("*.yaml"):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and "condition" in data:
                    cond = data["condition"]
                    if cond not in covered:
                        covered[cond] = "covered_seed"
            except Exception:
                continue

    return covered


def _assign_priority(
    condition: dict,
    coverage_status: str,
) -> str:
    """Assign priority based on risk tier and coverage status."""
    risk_tier = condition.get("risk_tier", "C")
    if coverage_status == "uncovered":
        if risk_tier == "A":
            return "P0"
        elif risk_tier == "B":
            return "P1"
        else:
            return "P2"
    else:
        # Covered but could be undertested
        return "P2"


def build_coverage_report(
    openem_conditions: list[dict] | None = None,
) -> dict:
    """Build the full coverage report.

    Returns:
        Dict with keys: conditions (list), summary (dict), by_category (dict),
        by_priority (dict).
    """
    if openem_conditions is None:
        openem_conditions = _load_openem_conditions()

    covered = _load_covered_conditions()

    conditions_report: list[dict] = []
    by_category: dict[str, dict] = {}
    by_priority: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}

    for cond in openem_conditions:
        cid = cond.get("condition_id", "unknown")
        category = cond.get("abem_category", cond.get("category", "unknown"))
        risk_tier = cond.get("risk_tier", "C")
        tth = cond.get("time_to_harm", "")
        has_confusion = bool(cond.get("confusion_pairs"))

        # Normalize condition_id for matching (hyphens → underscores)
        cid_normalized = cid.replace("-", "_")
        coverage_status = covered.get(cid_normalized, covered.get(cid, "uncovered"))

        priority = _assign_priority(cond, coverage_status)

        entry = {
            "condition_id": cid,
            "abem_category": category,
            "risk_tier": risk_tier,
            "time_to_harm": str(tth) if tth else "",
            "coverage_status": coverage_status,
            "has_confusion_pairs": has_confusion,
            "priority": priority,
        }
        conditions_report.append(entry)

        # Category stats
        if category not in by_category:
            by_category[category] = {"total": 0, "covered": 0, "uncovered": 0}
        by_category[category]["total"] += 1
        if coverage_status == "uncovered":
            by_category[category]["uncovered"] += 1
        else:
            by_category[category]["covered"] += 1

        by_priority[priority] += 1

    total = len(conditions_report)
    covered_count = sum(
        1 for c in conditions_report if c["coverage_status"] != "uncovered"
    )
    uncovered_count = total - covered_count

    summary = {
        "total_conditions": total,
        "covered": covered_count,
        "uncovered": uncovered_count,
        "coverage_pct": round(covered_count / total * 100, 1) if total > 0 else 0,
        "p0_uncovered": by_priority["P0"],
        "p1_uncovered": by_priority["P1"],
        "p2": by_priority["P2"],
    }

    return {
        "conditions": conditions_report,
        "summary": summary,
        "by_category": by_category,
        "by_priority": by_priority,
    }


def format_text(report: dict) -> str:
    """Format report as human-readable text table."""
    lines: list[str] = []
    summary = report["summary"]

    lines.append("=" * 72)
    lines.append("LOSTBENCH COVERAGE REPORT")
    lines.append("=" * 72)
    lines.append(
        f"Coverage: {summary['covered']}/{summary['total_conditions']} "
        f"({summary['coverage_pct']}%)"
    )
    lines.append(f"P0 uncovered (risk tier A): {summary['p0_uncovered']}")
    lines.append(f"P1 uncovered (risk tier B): {summary['p1_uncovered']}")
    lines.append("")

    # Category breakdown
    lines.append("BY ABEM CATEGORY")
    lines.append("-" * 72)
    lines.append(f"{'Category':<30} {'Covered':>8} {'Uncovered':>10} {'Total':>6}")
    lines.append("-" * 72)
    for cat, stats in sorted(report["by_category"].items()):
        lines.append(
            f"{cat:<30} {stats['covered']:>8} {stats['uncovered']:>10} {stats['total']:>6}"
        )

    # P0 uncovered conditions
    p0 = [c for c in report["conditions"] if c["priority"] == "P0"]
    if p0:
        lines.append("")
        lines.append(f"P0 UNCOVERED CONDITIONS ({len(p0)})")
        lines.append("-" * 72)
        for c in sorted(p0, key=lambda x: x["condition_id"]):
            confusion = " [confusion_pairs]" if c["has_confusion_pairs"] else ""
            tth = f" tth={c['time_to_harm']}" if c["time_to_harm"] else ""
            lines.append(
                f"  {c['condition_id']:<40} {c['abem_category']:<20}{tth}{confusion}"
            )

    return "\n".join(lines)


def format_summary(report: dict) -> str:
    """Format report as one-liner summary."""
    s = report["summary"]
    return (
        f"Coverage: {s['covered']}/{s['total_conditions']} ({s['coverage_pct']}%). "
        f"P0 uncovered: {s['p0_uncovered']}. P1: {s['p1_uncovered']}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LostBench coverage report — maps OpenEM conditions to scenario coverage"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "summary"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Write JSON output to .coverage_cache.json",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="  [%(name)s] %(message)s",
        stream=sys.stderr,
    )

    report = build_coverage_report()

    if args.format == "json":
        output = json.dumps(report, indent=2)
        print(output)
    elif args.format == "summary":
        print(format_summary(report))
    else:
        print(format_text(report))

    if args.cache:
        with open(CACHE_PATH, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nCache written to {CACHE_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
