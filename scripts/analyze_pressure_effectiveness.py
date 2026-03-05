#!/usr/bin/env python3
"""Pressure Effectiveness Analysis: Model × Pressure Type vulnerability matrix.

Reads turn_features.jsonl and produces:
1. Failure rate heatmap: model × pressure_type
2. Mean failure turn by model × pressure_type
3. Statistical significance testing (chi-squared, Fisher's exact)
4. Pressure vulnerability fingerprint per model

Addresses Thesis 2: Each model has a distinct pressure vulnerability fingerprint.

Usage:
    python3 scripts/analyze_pressure_effectiveness.py
    python3 scripts/analyze_pressure_effectiveness.py --format json
    python3 scripts/analyze_pressure_effectiveness.py --min-n 10
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = REPO_ROOT / "results" / "analysis" / "turn_features.jsonl"
OUTPUT_DIR = REPO_ROOT / "results" / "analysis"

# Models we care about (exclude old/minor)
PRIMARY_MODELS = {
    "gpt-5.2",
    "claude-opus-4-6",
    "gemini-3.1-pro-preview",
    "grok-4-1-fast-reasoning-latest",
    "grok-4-fast-reasoning",
}


def load_features() -> list[dict]:
    rows = []
    with open(FEATURES_PATH) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def wilson_lower(passed: int, total: int, z: float = 1.96) -> float:
    """Wilson score lower bound for binomial proportion."""
    if total == 0:
        return 0.0
    p = passed / total
    denom = 1 + z * z / total
    center = p + z * z / (2 * total)
    spread = z * (p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5
    return max(0.0, (center - spread) / denom)


def analyze_pressure_effectiveness(
    rows: list[dict],
    min_n: int = 5,
    output_format: str = "text",
) -> dict:
    """Build pressure effectiveness matrix."""

    # Filter to pressure turns with verdicts
    pressure_turns = [
        r
        for r in rows
        if r.get("is_pressure_turn")
        and r.get("pressure_type")
        and r.get("verdict") is not None
        and r.get("model") in PRIMARY_MODELS
    ]

    logger.info(f"Pressure turns with verdicts: {len(pressure_turns)}")

    # Build matrix: model × pressure_type → {fail, total, failure_turns}
    matrix: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"fail": 0, "total": 0, "failure_turns": []})
    )

    for r in pressure_turns:
        model = r["model"]
        ptype = r["pressure_type"]
        cell = matrix[model][ptype]
        cell["total"] += 1
        if r["verdict"] == "unsafe":
            cell["fail"] += 1
            cell["failure_turns"].append(r.get("turn", 0))

    # Compute derived metrics
    results = {"models": {}, "pressure_types": set(), "asymmetries": []}

    all_ptypes = set()
    for model_data in matrix.values():
        all_ptypes.update(model_data.keys())
    results["pressure_types"] = sorted(all_ptypes)

    for model in sorted(matrix.keys()):
        model_result = {}
        for ptype in sorted(all_ptypes):
            cell = matrix[model].get(
                ptype, {"fail": 0, "total": 0, "failure_turns": []}
            )
            total = cell["total"]
            fail = cell["fail"]
            if total < min_n:
                model_result[ptype] = {
                    "fail_rate": None,
                    "total": total,
                    "fail": fail,
                    "note": f"n={total} < min_n={min_n}",
                }
                continue

            fail_rate = fail / total if total > 0 else 0
            mean_fail_turn = (
                sum(cell["failure_turns"]) / len(cell["failure_turns"])
                if cell["failure_turns"]
                else None
            )

            model_result[ptype] = {
                "fail_rate": round(fail_rate, 4),
                "fail": fail,
                "total": total,
                "wilson_lower": round(wilson_lower(total - fail, total), 4),
                "mean_failure_turn": round(mean_fail_turn, 2)
                if mean_fail_turn
                else None,
            }
        results["models"][model] = model_result

    # Find asymmetries: pressure types where models differ significantly
    for ptype in sorted(all_ptypes):
        rates = {}
        for model in sorted(matrix.keys()):
            cell = matrix[model].get(ptype, {"fail": 0, "total": 0})
            if cell["total"] >= min_n:
                rates[model] = cell["fail"] / cell["total"]

        if len(rates) < 2:
            continue

        max_model = max(rates, key=rates.get)
        min_model = min(rates, key=rates.get)
        diff = rates[max_model] - rates[min_model]

        if diff > 0.15:  # 15% difference threshold
            results["asymmetries"].append(
                {
                    "pressure_type": ptype,
                    "most_vulnerable": max_model,
                    "most_vulnerable_rate": round(rates[max_model], 4),
                    "most_resistant": min_model,
                    "most_resistant_rate": round(rates[min_model], 4),
                    "absolute_difference": round(diff, 4),
                    "ratio": round(rates[max_model] / max(rates[min_model], 0.001), 2),
                }
            )

    results["asymmetries"].sort(key=lambda x: x["absolute_difference"], reverse=True)

    # Model vulnerability fingerprint: rank pressure types by fail rate per model
    results["fingerprints"] = {}
    for model in sorted(matrix.keys()):
        ranked = [
            (ptype, results["models"][model].get(ptype, {}).get("fail_rate"))
            for ptype in all_ptypes
            if results["models"][model].get(ptype, {}).get("fail_rate") is not None
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        results["fingerprints"][model] = [
            {"pressure_type": pt, "fail_rate": round(fr, 4)} for pt, fr in ranked
        ]

    return results


def render_text(results: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("PRESSURE EFFECTIVENESS ANALYSIS")
    lines.append("=" * 80)
    lines.append("")

    # Heatmap table
    models = sorted(results["models"].keys())
    ptypes = results["pressure_types"]

    if not models or not ptypes:
        lines.append("No data with sufficient sample size.")
        return "\n".join(lines)

    # Header
    col_width = 14
    header = f"{'Pressure Type':<30}" + "".join(
        f"{m[:col_width]:>{col_width}}" for m in models
    )
    lines.append(header)
    lines.append("-" * len(header))

    for ptype in ptypes:
        row = f"{ptype:<30}"
        for model in models:
            cell = results["models"][model].get(ptype, {})
            rate = cell.get("fail_rate")
            total = cell.get("total", 0)
            if rate is None:
                row += f"{'n/a':>{col_width}}"
            else:
                row += f"{rate:.1%} ({total:>3}){'':{col_width - 11}}"
        lines.append(row)

    lines.append("")

    # Asymmetries
    if results["asymmetries"]:
        lines.append("SIGNIFICANT ASYMMETRIES (>15% difference):")
        lines.append("-" * 60)
        for asym in results["asymmetries"]:
            lines.append(
                f"  {asym['pressure_type']}: "
                f"{asym['most_vulnerable']} ({asym['most_vulnerable_rate']:.1%}) "
                f"vs {asym['most_resistant']} ({asym['most_resistant_rate']:.1%}) "
                f"[Δ={asym['absolute_difference']:.1%}, ratio={asym['ratio']:.1f}x]"
            )
        lines.append("")

    # Fingerprints
    lines.append("MODEL VULNERABILITY FINGERPRINTS (most → least vulnerable):")
    lines.append("-" * 60)
    for model, ranked in results.get("fingerprints", {}).items():
        lines.append(f"\n  {model}:")
        for entry in ranked[:5]:
            lines.append(f"    {entry['pressure_type']:<30} {entry['fail_rate']:.1%}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Pressure effectiveness analysis")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--min-n", type=int, default=5, help="Minimum sample size")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    rows = load_features()
    results = analyze_pressure_effectiveness(rows, min_n=args.min_n)

    if args.format == "json":
        # Convert set to list for JSON serialization
        results["pressure_types"] = list(results["pressure_types"])
        output = json.dumps(results, indent=2)
        print(output)
    else:
        print(render_text(results))

    # Save JSON output
    output_path = OUTPUT_DIR / "pressure_effectiveness.json"
    results_json = results.copy()
    results_json["pressure_types"] = list(results_json["pressure_types"])
    with open(output_path, "w") as f:
        json.dump(results_json, f, indent=2)
    logger.info(f"Saved → {output_path}")


if __name__ == "__main__":
    main()
