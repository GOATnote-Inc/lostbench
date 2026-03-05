#!/usr/bin/env python3
"""Response Length Analysis: Correlation between response length and safety outcome.

Tests Thesis 3: Longer responses are either safer (more room to maintain escalation)
or more dangerous (more surface area for operationally substitutive content).

Also tests Thesis 10: High token consumption = model uncertainty = capitulation risk.

Usage:
    python3 scripts/analyze_response_length.py
    python3 scripts/analyze_response_length.py --format json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
FEATURES_PATH = REPO_ROOT / "results" / "analysis" / "turn_features.jsonl"
OUTPUT_DIR = REPO_ROOT / "results" / "analysis"


def load_features() -> list[dict]:
    rows = []
    with open(FEATURES_PATH) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def pearson_r(xs: list[float], ys: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    sx = (sum((x - mx) ** 2 for x in xs) / n) ** 0.5
    sy = (sum((y - my) ** 2 for y in ys) / n) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def point_biserial(continuous: list[float], binary: list[int]) -> float:
    """Point-biserial correlation between continuous variable and binary outcome."""
    if len(continuous) != len(binary) or len(continuous) < 3:
        return 0.0
    group0 = [c for c, b in zip(continuous, binary) if b == 0]
    group1 = [c for c, b in zip(continuous, binary) if b == 1]
    if not group0 or not group1:
        return 0.0
    m0 = sum(group0) / len(group0)
    m1 = sum(group1) / len(group1)
    n = len(continuous)
    n0 = len(group0)
    n1 = len(group1)
    overall_std = (sum((c - sum(continuous) / n) ** 2 for c in continuous) / n) ** 0.5
    if overall_std == 0:
        return 0.0
    return (m1 - m0) / overall_std * (n0 * n1 / (n * n)) ** 0.5


def cohens_d(group1: list[float], group2: list[float]) -> float:
    """Cohen's d effect size."""
    if len(group1) < 2 or len(group2) < 2:
        return 0.0
    m1, m2 = sum(group1) / len(group1), sum(group2) / len(group2)
    var1 = sum((x - m1) ** 2 for x in group1) / (len(group1) - 1)
    var2 = sum((x - m2) ** 2 for x in group2) / (len(group2) - 1)
    pooled_std = (
        ((len(group1) - 1) * var1 + (len(group2) - 1) * var2)
        / (len(group1) + len(group2) - 2)
    ) ** 0.5
    if pooled_std == 0:
        return 0.0
    return (m1 - m2) / pooled_std


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return 0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def analyze_response_length(rows: list[dict]) -> dict:
    """Analyze correlation between response length and safety outcomes."""

    # Filter to rows with verdicts and response content
    graded = [
        r
        for r in rows
        if r.get("verdict") is not None and r.get("response_chars", 0) > 0
    ]

    results = {
        "total_graded_turns": len(graded),
        "overall": {},
        "by_model": {},
        "by_turn": {},
        "by_verdict": {},
        "length_bins": {},
    }

    # Overall: safe vs unsafe response lengths
    safe_lengths = [r["response_chars"] for r in graded if r["verdict"] == "safe"]
    unsafe_lengths = [r["response_chars"] for r in graded if r["verdict"] == "unsafe"]

    results["overall"] = {
        "safe_mean": round(sum(safe_lengths) / len(safe_lengths))
        if safe_lengths
        else 0,
        "safe_median": round(percentile(safe_lengths, 50)),
        "unsafe_mean": round(sum(unsafe_lengths) / len(unsafe_lengths))
        if unsafe_lengths
        else 0,
        "unsafe_median": round(percentile(unsafe_lengths, 50)),
        "cohens_d": round(cohens_d(safe_lengths, unsafe_lengths), 4),
        "n_safe": len(safe_lengths),
        "n_unsafe": len(unsafe_lengths),
        "point_biserial_r": round(
            point_biserial(
                [r["response_chars"] for r in graded],
                [1 if r["verdict"] == "safe" else 0 for r in graded],
            ),
            4,
        ),
    }

    # By model
    models = set(r.get("model", "") for r in graded)
    for model in sorted(models):
        model_rows = [r for r in graded if r.get("model") == model]
        s = [r["response_chars"] for r in model_rows if r["verdict"] == "safe"]
        u = [r["response_chars"] for r in model_rows if r["verdict"] == "unsafe"]
        if not s or not u:
            continue

        results["by_model"][model] = {
            "safe_mean": round(sum(s) / len(s)),
            "safe_median": round(percentile(s, 50)),
            "unsafe_mean": round(sum(u) / len(u)),
            "unsafe_median": round(percentile(u, 50)),
            "cohens_d": round(cohens_d(s, u), 4),
            "n_safe": len(s),
            "n_unsafe": len(u),
            "direction": "safe_longer"
            if sum(s) / len(s) > sum(u) / len(u)
            else "unsafe_longer",
        }

    # By turn (do responses get shorter under pressure?)
    for turn in range(1, 6):
        turn_rows = [r for r in graded if r.get("turn") == turn]
        if not turn_rows:
            continue
        lengths = [r["response_chars"] for r in turn_rows]
        safe_rate = sum(1 for r in turn_rows if r["verdict"] == "safe") / len(turn_rows)
        results["by_turn"][str(turn)] = {
            "mean_length": round(sum(lengths) / len(lengths)),
            "median_length": round(percentile(lengths, 50)),
            "safe_rate": round(safe_rate, 4),
            "n": len(turn_rows),
        }

    # Length bins: quartile analysis
    all_lengths = sorted(r["response_chars"] for r in graded)
    q25 = percentile(all_lengths, 25)
    q50 = percentile(all_lengths, 50)
    q75 = percentile(all_lengths, 75)

    bins = [
        ("Q1 (shortest)", lambda x: x <= q25),
        ("Q2", lambda x: q25 < x <= q50),
        ("Q3", lambda x: q50 < x <= q75),
        ("Q4 (longest)", lambda x: x > q75),
    ]

    for bin_name, pred in bins:
        bin_rows = [r for r in graded if pred(r["response_chars"])]
        if not bin_rows:
            continue
        safe_rate = sum(1 for r in bin_rows if r["verdict"] == "safe") / len(bin_rows)
        results["length_bins"][bin_name] = {
            "safe_rate": round(safe_rate, 4),
            "n": len(bin_rows),
            "mean_chars": round(
                sum(r["response_chars"] for r in bin_rows) / len(bin_rows)
            ),
        }

    # Thesis 10: Judge confidence vs response length
    judge_rows = [
        r
        for r in graded
        if r.get("judge_confidence") is not None and r.get("judge_confidence") > 0
    ]
    if len(judge_rows) >= 10:
        lengths_j = [r["response_chars"] for r in judge_rows]
        confidences = [r["judge_confidence"] for r in judge_rows]
        results["judge_confidence_correlation"] = {
            "pearson_r": round(pearson_r(lengths_j, confidences), 4),
            "n": len(judge_rows),
        }

    return results


def render_text(results: dict) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("RESPONSE LENGTH ANALYSIS")
    lines.append("=" * 80)
    lines.append(f"\nTotal graded turns: {results['total_graded_turns']}")

    o = results["overall"]
    lines.append("\nOVERALL:")
    lines.append("-" * 50)
    lines.append(
        f"  Safe responses:   mean={o['safe_mean']:,} chars, "
        f"median={o['safe_median']:,} chars (n={o['n_safe']})"
    )
    lines.append(
        f"  Unsafe responses: mean={o['unsafe_mean']:,} chars, "
        f"median={o['unsafe_median']:,} chars (n={o['n_unsafe']})"
    )
    lines.append(f"  Cohen's d: {o['cohens_d']:+.4f}")
    lines.append(f"  Point-biserial r: {o['point_biserial_r']:+.4f}")
    direction = (
        "Safe responses are longer"
        if o["cohens_d"] > 0
        else "Unsafe responses are longer"
    )
    strength = (
        "negligible"
        if abs(o["cohens_d"]) < 0.2
        else "small"
        if abs(o["cohens_d"]) < 0.5
        else "medium"
        if abs(o["cohens_d"]) < 0.8
        else "large"
    )
    lines.append(f"  → {direction} ({strength} effect)")

    lines.append("\nBY MODEL:")
    lines.append("-" * 70)
    for model, data in sorted(results.get("by_model", {}).items()):
        lines.append(
            f"  {model}: safe_mean={data['safe_mean']:,} vs unsafe_mean={data['unsafe_mean']:,} "
            f"(d={data['cohens_d']:+.3f}, {data['direction']})"
        )

    lines.append("\nBY TURN (response length under increasing pressure):")
    lines.append("-" * 60)
    for turn, data in sorted(results.get("by_turn", {}).items()):
        lines.append(
            f"  Turn {turn}: mean={data['mean_length']:,} chars, "
            f"safe_rate={data['safe_rate']:.1%} (n={data['n']})"
        )

    lines.append("\nLENGTH QUARTILE → SAFETY RATE:")
    lines.append("-" * 50)
    for bin_name, data in results.get("length_bins", {}).items():
        lines.append(
            f"  {bin_name:<20} safe_rate={data['safe_rate']:.1%} "
            f"(mean={data['mean_chars']:,} chars, n={data['n']})"
        )

    if "judge_confidence_correlation" in results:
        jc = results["judge_confidence_correlation"]
        lines.append("\nJUDGE CONFIDENCE vs RESPONSE LENGTH:")
        lines.append(f"  Pearson r = {jc['pearson_r']:+.4f} (n={jc['n']})")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Response length analysis")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    rows = load_features()
    results = analyze_response_length(rows)

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(render_text(results))

    output_path = OUTPUT_DIR / "response_length_analysis.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved → {output_path}")


if __name__ == "__main__":
    main()
