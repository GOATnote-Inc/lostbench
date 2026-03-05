#!/usr/bin/env python3
"""Cross-Repo Correlation: ScribeGoat2 ↔ LostBench behavioral comparison.

Matches SG2 bloom_eval_v2 trajectories to LostBench scenarios by condition,
compares behavioral features, and enriches with OpenEM clinical metadata.

Addresses Phase 3: Cross-repo correlation for conditions evaluated by both systems.

Usage:
    python3 scripts/correlate_sg2_lb.py
    python3 scripts/correlate_sg2_lb.py --format json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
LB_FEATURES = REPO_ROOT / "results" / "analysis" / "turn_features.jsonl"
OUTPUT_DIR = REPO_ROOT / "results" / "analysis"

SG2_ROOT = Path.home() / "scribegoat2"
SG2_RESULTS = SG2_ROOT / "evaluation" / "bloom_eval_v2" / "results"

OPENEM_ROOT = Path.home() / "openem-corpus"

# Map scenario IDs to conditions for cross-referencing
# (SG2 uses same scenario IDs as LB for shared scenarios)


def load_lb_features() -> list[dict]:
    """Load LostBench turn features."""
    rows = []
    with open(LB_FEATURES) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def load_sg2_results() -> list[dict]:
    """Load all ScribeGoat2 bloom_eval_v2 results."""
    results = []
    if not SG2_RESULTS.exists():
        logger.warning(f"SG2 results not found: {SG2_RESULTS}")
        return results

    for json_file in sorted(SG2_RESULTS.glob("bloom_eval_*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
            for entry in data.get("results", []):
                entry["_source_file"] = json_file.name
                entry["_run_id"] = data.get("metadata", {}).get("run_id", "")
                results.append(entry)
        except Exception as e:
            logger.debug(f"Error loading {json_file}: {e}")

    # Also check subdirectory results
    for subdir in SG2_RESULTS.iterdir():
        if not subdir.is_dir():
            continue
        for json_file in sorted(subdir.glob("*.json")):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                if isinstance(data, dict) and "results" in data:
                    for entry in data["results"]:
                        entry["_source_file"] = f"{subdir.name}/{json_file.name}"
                        results.append(entry)
                elif isinstance(data, list):
                    for entry in data:
                        entry["_source_file"] = f"{subdir.name}/{json_file.name}"
                        results.append(entry)
            except Exception:
                pass

    return results


def load_openem_metadata() -> dict[str, dict]:
    """Load OpenEM condition metadata for enrichment."""
    metadata = {}

    # Try loading condition map
    try:
        sys.path.insert(0, str(OPENEM_ROOT / "python"))
        from openem.conditions import load_condition_map

        cmap = load_condition_map()
        for entry in cmap:
            cid = entry.get("condition_id", "")
            metadata[cid] = {
                "category": entry.get("category"),
                "icd10": entry.get("icd10"),
                "tier": entry.get("tier"),
                "time_to_harm": entry.get("evaluation_properties", {}).get(
                    "time_to_harm"
                ),
                "pressure_vulnerability": entry.get("evaluation_properties", {}).get(
                    "pressure_vulnerability"
                ),
            }
    except Exception as e:
        logger.debug(f"OpenEM condition map not available: {e}")

        # Fallback: try loading from JSON files
        conditions_dir = OPENEM_ROOT / "conditions"
        if conditions_dir.exists():
            for yaml_file in conditions_dir.rglob("*.yaml"):
                try:
                    import yaml

                    with open(yaml_file) as f:
                        cond = yaml.safe_load(f)
                    if cond and "condition_id" in cond:
                        metadata[cond["condition_id"]] = {
                            "category": cond.get("category"),
                            "icd10": cond.get("icd10"),
                            "tier": cond.get("tier"),
                        }
                except Exception:
                    pass

    return metadata


def correlate(
    lb_rows: list[dict],
    sg2_results: list[dict],
    openem_meta: dict[str, dict],
) -> dict:
    """Cross-correlate LostBench and ScribeGoat2 results by condition."""

    # Build LB condition-level aggregates
    lb_by_condition: dict[str, dict] = defaultdict(
        lambda: {
            "n_turns": 0,
            "n_safe": 0,
            "n_unsafe": 0,
            "models": set(),
            "mean_hedging": [],
            "mean_imperative": [],
            "mean_response_chars": [],
            "scenarios": set(),
        }
    )

    for r in lb_rows:
        cond = r.get("condition", "")
        if not cond:
            continue
        cell = lb_by_condition[cond]
        cell["n_turns"] += 1
        if r.get("verdict") == "safe":
            cell["n_safe"] += 1
        elif r.get("verdict") == "unsafe":
            cell["n_unsafe"] += 1
        cell["models"].add(r.get("model", ""))
        cell["mean_hedging"].append(r.get("hedging_count", 0))
        cell["mean_imperative"].append(r.get("imperative_count", 0))
        cell["mean_response_chars"].append(r.get("response_chars", 0))
        cell["scenarios"].add(r.get("scenario_id", ""))

    # Build SG2 condition-level aggregates
    sg2_by_condition: dict[str, dict] = defaultdict(
        lambda: {
            "n_trials": 0,
            "n_passed": 0,
            "n_failed": 0,
            "outcomes": [],
            "models": set(),
            "mean_severity": [],
            "scenarios": set(),
        }
    )

    # Map SG2 scenario IDs to conditions (SG2 uses same MTR-xxx IDs)
    for entry in sg2_results:
        # SG2 doesn't always have condition directly — use scenario_id
        sid = entry.get("scenario_id", "")
        model = entry.get("model_id", "")

        cell = sg2_by_condition[sid]
        cell["n_trials"] += 1
        if entry.get("passed"):
            cell["n_passed"] += 1
        else:
            cell["n_failed"] += 1
        cell["outcomes"].append(entry.get("outcome", ""))
        cell["models"].add(model)
        cell["mean_severity"].append(entry.get("severity_score", 0))
        cell["scenarios"].add(sid)

    # Find overlapping scenarios/conditions
    lb_scenarios = set()
    for cond_data in lb_by_condition.values():
        lb_scenarios.update(cond_data["scenarios"])

    sg2_scenarios = set()
    for cond_data in sg2_by_condition.values():
        sg2_scenarios.update(cond_data["scenarios"])

    overlap = lb_scenarios & sg2_scenarios

    # Build correlation entries for overlapping scenarios
    correlations = []
    for sid in sorted(overlap):
        lb_data = None
        sg2_data = sg2_by_condition.get(sid)

        # Find matching LB data by scenario_id
        for cond, data in lb_by_condition.items():
            if sid in data["scenarios"]:
                lb_data = data
                break

        if not lb_data or not sg2_data:
            continue

        lb_safe_rate = (
            lb_data["n_safe"] / (lb_data["n_safe"] + lb_data["n_unsafe"])
            if (lb_data["n_safe"] + lb_data["n_unsafe"]) > 0
            else None
        )
        sg2_pass_rate = (
            sg2_data["n_passed"] / sg2_data["n_trials"]
            if sg2_data["n_trials"] > 0
            else None
        )

        def mean(xs):
            valid = [x for x in xs if x is not None]
            return sum(valid) / len(valid) if valid else 0

        entry = {
            "scenario_id": sid,
            "lb_safe_rate": round(lb_safe_rate, 4)
            if lb_safe_rate is not None
            else None,
            "sg2_pass_rate": round(sg2_pass_rate, 4)
            if sg2_pass_rate is not None
            else None,
            "lb_n_turns": lb_data["n_turns"],
            "sg2_n_trials": sg2_data["n_trials"],
            "lb_models": sorted(lb_data["models"]),
            "sg2_models": sorted(sg2_data["models"]),
            "lb_mean_hedging": round(mean(lb_data["mean_hedging"]), 2),
            "lb_mean_imperative": round(mean(lb_data["mean_imperative"]), 2),
            "lb_mean_response_chars": round(mean(lb_data["mean_response_chars"])),
            "sg2_mean_severity": round(mean(sg2_data["mean_severity"]), 2),
            "sg2_outcomes": dict(
                __import__("collections").Counter(sg2_data["outcomes"])
            ),
        }

        # Agreement check
        if lb_safe_rate is not None and sg2_pass_rate is not None:
            entry["agreement"] = (
                "concordant"
                if abs(lb_safe_rate - sg2_pass_rate) < 0.2
                else "discordant"
            )
            entry["rate_delta"] = round(lb_safe_rate - sg2_pass_rate, 4)

        correlations.append(entry)

    results = {
        "lb_conditions": len(lb_by_condition),
        "sg2_scenarios": len(sg2_by_condition),
        "overlapping_scenarios": len(overlap),
        "overlap_list": sorted(overlap),
        "correlations": correlations,
        "summary": {},
    }

    # Summary statistics
    if correlations:
        concordant = sum(1 for c in correlations if c.get("agreement") == "concordant")
        discordant = sum(1 for c in correlations if c.get("agreement") == "discordant")
        deltas = [c["rate_delta"] for c in correlations if "rate_delta" in c]

        results["summary"] = {
            "concordant": concordant,
            "discordant": discordant,
            "concordance_rate": round(concordant / (concordant + discordant), 4)
            if (concordant + discordant) > 0
            else None,
            "mean_rate_delta": round(sum(deltas) / len(deltas), 4) if deltas else None,
            "lb_stricter": sum(1 for d in deltas if d < -0.1),
            "sg2_stricter": sum(1 for d in deltas if d > 0.1),
        }

    return results


def render_text(results: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("CROSS-REPO CORRELATION: ScribeGoat2 ↔ LostBench")
    lines.append("=" * 80)

    lines.append(f"\nLostBench conditions: {results['lb_conditions']}")
    lines.append(f"ScribeGoat2 scenarios: {results['sg2_scenarios']}")
    lines.append(f"Overlapping scenarios: {results['overlapping_scenarios']}")

    if results.get("summary"):
        s = results["summary"]
        lines.append("\nCONCORDANCE SUMMARY:")
        lines.append(f"  Concordant: {s.get('concordant', 0)}")
        lines.append(f"  Discordant: {s.get('discordant', 0)}")
        lines.append(
            f"  Concordance rate: {s['concordance_rate']:.1%}"
            if s.get("concordance_rate") is not None
            else "  Concordance rate: n/a"
        )
        lines.append(
            f"  Mean rate delta (LB - SG2): {s['mean_rate_delta']:+.4f}"
            if s.get("mean_rate_delta") is not None
            else ""
        )
        lines.append(f"  LB stricter: {s.get('lb_stricter', 0)}")
        lines.append(f"  SG2 stricter: {s.get('sg2_stricter', 0)}")

    if results.get("correlations"):
        lines.append("\nPER-SCENARIO COMPARISON:")
        lines.append("-" * 80)
        lines.append(
            f"{'Scenario':<12} {'LB safe%':>10} {'SG2 pass%':>10} "
            f"{'Delta':>8} {'Agreement':<12} {'LB turns':>10} {'SG2 trials':>10}"
        )
        lines.append("-" * 80)
        for c in results["correlations"]:
            lb_r = (
                f"{c['lb_safe_rate']:.1%}"
                if c.get("lb_safe_rate") is not None
                else "n/a"
            )
            sg2_r = (
                f"{c['sg2_pass_rate']:.1%}"
                if c.get("sg2_pass_rate") is not None
                else "n/a"
            )
            delta = f"{c['rate_delta']:+.3f}" if "rate_delta" in c else "n/a"
            agree = c.get("agreement", "n/a")
            lines.append(
                f"{c['scenario_id']:<12} {lb_r:>10} {sg2_r:>10} "
                f"{delta:>8} {agree:<12} {c['lb_n_turns']:>10} {c['sg2_n_trials']:>10}"
            )

    if not results.get("correlations"):
        lines.append(
            "\nNo overlapping scenarios found between LostBench and ScribeGoat2."
        )
        lines.append(
            "This may be expected if the repos use different scenario ID schemes."
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Cross-repo correlation: SG2 ↔ LostBench"
    )
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    logger.info("Loading LostBench features...")
    lb_rows = load_lb_features()

    logger.info("Loading ScribeGoat2 results...")
    sg2_results = load_sg2_results()
    logger.info(f"  SG2 results: {len(sg2_results)}")

    logger.info("Loading OpenEM metadata...")
    openem_meta = load_openem_metadata()
    logger.info(f"  OpenEM conditions: {len(openem_meta)}")

    results = correlate(lb_rows, sg2_results, openem_meta)

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(render_text(results))

    output_path = OUTPUT_DIR / "cross_repo_correlation.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved → {output_path}")


if __name__ == "__main__":
    main()
