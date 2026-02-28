#!/usr/bin/env python3
"""Compare original Sonnet 4.5 grades with cross-vendor grades for MSTS Studies 2+3.

Loads original grading from challenge metadata (preserved by import_msts.py) and
new cross-vendor grades, then computes:
  - Per-model failure rate under each grading method
  - Agreement matrix (Sonnet 4.5 vs cross-vendor verdict)
  - Cohen's kappa for inter-judge reliability
  - The 80x ratio before and after
  - Per-condition breakdown

Usage:
    python3 scripts/compare_msts_judges.py
    python3 scripts/compare_msts_judges.py --study 2
    python3 scripts/compare_msts_judges.py --results-dir results/msts-crossvendor-v2
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lostbench.challenge import ChallengeResult
from lostbench.grader import GradeResult

logger = logging.getLogger("compare_msts")

IMPORT_DIR = Path(__file__).parent.parent / "results" / "msts-import"
DEFAULT_CROSSVENDOR_DIR = Path(__file__).parent.parent / "results" / "msts-crossvendor"


def load_original_grades() -> dict[str, dict]:
    """Load original Sonnet 4.5 grades from challenge metadata.

    Returns {scenario_id: {model, study, classification, hard_failure, ...}}
    """
    originals = {}
    if not IMPORT_DIR.exists():
        logger.error("Import dir not found: %s", IMPORT_DIR)
        return originals

    for subdir in sorted(IMPORT_DIR.iterdir()):
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.glob("challenge_*.json")):
            challenge = ChallengeResult.load(path)
            meta = challenge.metadata
            original_grading = meta.get("original_grading", {})

            hard_failure = original_grading.get("hard_failure", {})
            classification = original_grading.get("classification", "")

            # Determine pass/fail from original grading
            original_failed = hard_failure.get("detected", False)

            originals[challenge.scenario_id] = {
                "model": challenge.model,
                "condition": challenge.condition,
                "study": meta.get("study", 0),
                "vignette_id": meta.get("vignette_id", ""),
                "original_failed": original_failed,
                "original_classification": classification,
                "original_failure_type": hard_failure.get("failure_type"),
                "original_confidence": hard_failure.get("confidence", ""),
                "original_turn": hard_failure.get("turn"),
                "original_judge": meta.get("original_judge_model", ""),
            }

    return originals


def load_crossvendor_grades(
    crossvendor_dir: Path | None = None,
) -> dict[str, GradeResult]:
    """Load cross-vendor grade results."""
    target_dir = crossvendor_dir or DEFAULT_CROSSVENDOR_DIR
    grades = {}
    if not target_dir.exists():
        logger.warning("Cross-vendor dir not found: %s", target_dir)
        return grades

    for subdir in sorted(target_dir.iterdir()):
        if not subdir.is_dir() or subdir.name in ("cache",):
            continue
        for path in sorted(subdir.glob("grade_*.json")):
            try:
                grade = GradeResult.load(path)
                grades[grade.scenario_id] = grade
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)

    return grades


def compute_cohens_kappa(
    agree_pass: int,
    agree_fail: int,
    sonnet_only_fail: int,
    crossvendor_only_fail: int,
) -> float:
    """Compute Cohen's kappa for inter-rater agreement."""
    n = agree_pass + agree_fail + sonnet_only_fail + crossvendor_only_fail
    if n == 0:
        return 0.0

    observed_agreement = (agree_pass + agree_fail) / n

    # Expected agreement by chance
    p_sonnet_fail = (agree_fail + sonnet_only_fail) / n
    p_crossvendor_fail = (agree_fail + crossvendor_only_fail) / n
    p_sonnet_pass = 1 - p_sonnet_fail
    p_crossvendor_pass = 1 - p_crossvendor_fail

    expected_agreement = (p_sonnet_fail * p_crossvendor_fail) + (
        p_sonnet_pass * p_crossvendor_pass
    )

    if expected_agreement == 1.0:
        return 1.0

    return (observed_agreement - expected_agreement) / (1 - expected_agreement)


def compute_cohens_h(p1: float, p2: float) -> float:
    """Compute Cohen's h effect size for two proportions."""
    phi1 = 2 * math.asin(math.sqrt(max(0, min(1, p1))))
    phi2 = 2 * math.asin(math.sqrt(max(0, min(1, p2))))
    return abs(phi2 - phi1)


def compare(
    study_filter: int | None = None, crossvendor_dir: Path | None = None
) -> dict:
    """Run comparison analysis."""
    originals = load_original_grades()
    crossvendor = load_crossvendor_grades(crossvendor_dir)

    logger.info(
        "Loaded %d original grades, %d cross-vendor grades",
        len(originals),
        len(crossvendor),
    )

    # Find matched pairs
    matched = []
    for sid in sorted(originals.keys()):
        if sid in crossvendor:
            orig = originals[sid]
            if study_filter and orig["study"] != study_filter:
                continue
            matched.append((sid, orig, crossvendor[sid]))

    logger.info("Matched pairs: %d", len(matched))
    if not matched:
        logger.error(
            "No matched pairs found. Run import_msts.py and regrade_msts_crossvendor.py first."
        )
        return {}

    # --- Per-model analysis ---
    by_model = defaultdict(list)
    for sid, orig, grade in matched:
        by_model[orig["model"]].append((sid, orig, grade))

    results = {
        "n_matched": len(matched),
        "models": {},
    }

    for model in sorted(by_model.keys()):
        pairs = by_model[model]
        n = len(pairs)

        # Original (Sonnet 4.5) verdicts
        sonnet_failures = sum(1 for _, orig, _ in pairs if orig["original_failed"])
        sonnet_failure_rate = sonnet_failures / n if n else 0

        # Cross-vendor verdicts
        crossvendor_failures = sum(1 for _, _, grade in pairs if not grade.passed)
        crossvendor_failure_rate = crossvendor_failures / n if n else 0

        # Agreement matrix
        agree_pass = sum(
            1
            for _, orig, grade in pairs
            if not orig["original_failed"] and grade.passed
        )
        agree_fail = sum(
            1
            for _, orig, grade in pairs
            if orig["original_failed"] and not grade.passed
        )
        sonnet_only_fail = sum(
            1 for _, orig, grade in pairs if orig["original_failed"] and grade.passed
        )
        crossvendor_only_fail = sum(
            1
            for _, orig, grade in pairs
            if not orig["original_failed"] and not grade.passed
        )

        agreement_rate = (agree_pass + agree_fail) / n if n else 0
        kappa = compute_cohens_kappa(
            agree_pass, agree_fail, sonnet_only_fail, crossvendor_only_fail
        )

        # Per-condition breakdown
        by_condition = defaultdict(list)
        for sid, orig, grade in pairs:
            by_condition[orig["condition"]].append((sid, orig, grade))

        condition_results = {}
        for condition in sorted(by_condition.keys()):
            cpairs = by_condition[condition]
            cn = len(cpairs)
            c_sonnet_fail = sum(1 for _, o, _ in cpairs if o["original_failed"])
            c_cross_fail = sum(1 for _, _, g in cpairs if not g.passed)
            c_classA = sum(g.classA for _, _, g in cpairs)
            condition_results[condition] = {
                "n": cn,
                "sonnet_failure_rate": c_sonnet_fail / cn if cn else 0,
                "crossvendor_failure_rate": c_cross_fail / cn if cn else 0,
                "classA": c_classA,
            }

        judge_model = crossvendor[pairs[0][0]].judge_model if pairs else ""

        results["models"][model] = {
            "n": n,
            "judge_model": judge_model,
            "sonnet_failure_rate": sonnet_failure_rate,
            "crossvendor_failure_rate": crossvendor_failure_rate,
            "agreement": {
                "agree_pass": agree_pass,
                "agree_fail": agree_fail,
                "sonnet_only_fail": sonnet_only_fail,
                "crossvendor_only_fail": crossvendor_only_fail,
                "agreement_rate": agreement_rate,
                "cohens_kappa": kappa,
            },
            "conditions": condition_results,
        }

    # --- 80x ratio analysis ---
    model_failure_rates_sonnet = {}
    model_failure_rates_crossvendor = {}
    for model, data in results["models"].items():
        model_failure_rates_sonnet[model] = data["sonnet_failure_rate"]
        model_failure_rates_crossvendor[model] = data["crossvendor_failure_rate"]

    gpt_model = next((m for m in results["models"] if "gpt" in m.lower()), None)
    opus_model = next((m for m in results["models"] if "opus" in m.lower()), None)

    if gpt_model and opus_model:
        gpt_sonnet_fr = model_failure_rates_sonnet[gpt_model]
        opus_sonnet_fr = model_failure_rates_sonnet[opus_model]
        gpt_cross_fr = model_failure_rates_crossvendor[gpt_model]
        opus_cross_fr = model_failure_rates_crossvendor[opus_model]

        sonnet_ratio = (
            opus_sonnet_fr / gpt_sonnet_fr if gpt_sonnet_fr > 0 else float("inf")
        )
        cross_ratio = opus_cross_fr / gpt_cross_fr if gpt_cross_fr > 0 else float("inf")

        results["ratio_analysis"] = {
            "gpt_model": gpt_model,
            "opus_model": opus_model,
            "sonnet_judge": {
                "gpt_failure_rate": gpt_sonnet_fr,
                "opus_failure_rate": opus_sonnet_fr,
                "ratio": sonnet_ratio,
            },
            "crossvendor_judge": {
                "gpt_failure_rate": gpt_cross_fr,
                "opus_failure_rate": opus_cross_fr,
                "ratio": cross_ratio,
            },
            "ratio_change": f"{sonnet_ratio:.1f}x → {cross_ratio:.1f}x",
            "effect_size_h": compute_cohens_h(gpt_cross_fr, opus_cross_fr),
        }

    return results


def print_report(results: dict) -> None:
    """Print human-readable comparison report."""
    if not results:
        return

    print("\n" + "=" * 80)
    print("MSTS CROSS-VENDOR REGRADE — COMPARISON REPORT")
    print("=" * 80)
    print(f"\nMatched trajectories: {results['n_matched']}")

    for model, data in sorted(results["models"].items()):
        judge = data["judge_model"]
        n = data["n"]
        print(f"\n{'─' * 60}")
        print(f"Model: {model} (N={n})")
        print(f"Cross-vendor judge: {judge}")
        print(f"\n  Sonnet 4.5 failure rate: {data['sonnet_failure_rate']:.3%}")
        print(f"  Cross-vendor failure rate: {data['crossvendor_failure_rate']:.3%}")

        agr = data["agreement"]
        print("\n  Agreement matrix:")
        print(f"    Both pass:           {agr['agree_pass']:>5}")
        print(f"    Both fail:           {agr['agree_fail']:>5}")
        print(f"    Sonnet-only fail:    {agr['sonnet_only_fail']:>5}")
        print(f"    Cross-vendor-only:   {agr['crossvendor_only_fail']:>5}")
        print(f"    Agreement rate:      {agr['agreement_rate']:.1%}")
        print(f"    Cohen's κ:           {agr['cohens_kappa']:.3f}")

        print("\n  Per-condition:")
        for cond, cdata in sorted(data["conditions"].items()):
            print(
                f"    {cond:<35} Sonnet {cdata['sonnet_failure_rate']:.1%} → "
                f"Cross {cdata['crossvendor_failure_rate']:.1%} "
                f"(N={cdata['n']}, classA={cdata['classA']})"
            )

    # 80x ratio
    if "ratio_analysis" in results:
        ra = results["ratio_analysis"]
        print(f"\n{'=' * 60}")
        print("80x RATIO ANALYSIS")
        print(f"{'=' * 60}")
        print(f"\n  GPT model:  {ra['gpt_model']}")
        print(f"  Opus model: {ra['opus_model']}")
        print("\n  Under Sonnet 4.5 judge:")
        s = ra["sonnet_judge"]
        print(f"    GPT failure:  {s['gpt_failure_rate']:.3%}")
        print(f"    Opus failure: {s['opus_failure_rate']:.3%}")
        print(f"    Ratio: {s['ratio']:.1f}x")
        print("\n  Under cross-vendor judge:")
        c = ra["crossvendor_judge"]
        print(f"    GPT failure:  {c['gpt_failure_rate']:.3%}")
        print(f"    Opus failure: {c['opus_failure_rate']:.3%}")
        print(f"    Ratio: {c['ratio']:.1f}x")
        print(f"\n  Ratio change: {ra['ratio_change']}")
        print(f"  Effect size (Cohen's h): {ra['effect_size_h']:.3f}")


def save_report(results: dict, output_dir: Path | None = None) -> None:
    """Save comparison results as JSON and markdown."""
    if not results:
        return

    target_dir = output_dir or DEFAULT_CROSSVENDOR_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = target_dir / "comparison_summary.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("JSON saved: %s", json_path)

    # Markdown
    md_path = target_dir / "comparison_report.md"
    lines = [
        "# MSTS Cross-Vendor Regrade — Comparison Report\n",
        f"Matched trajectories: {results['n_matched']}\n",
    ]

    for model, data in sorted(results["models"].items()):
        lines.append(f"\n## {model}\n")
        lines.append(f"- Judge: {data['judge_model']}")
        lines.append(f"- N: {data['n']}")
        lines.append(f"- Sonnet 4.5 failure rate: {data['sonnet_failure_rate']:.3%}")
        lines.append(
            f"- Cross-vendor failure rate: {data['crossvendor_failure_rate']:.3%}"
        )
        agr = data["agreement"]
        lines.append(f"- Agreement rate: {agr['agreement_rate']:.1%}")
        lines.append(f"- Cohen's κ: {agr['cohens_kappa']:.3f}\n")

        lines.append("| Condition | N | Sonnet FR | Cross FR | Class A |")
        lines.append("|-----------|---|-----------|----------|---------|")
        for cond, cdata in sorted(data["conditions"].items()):
            lines.append(
                f"| {cond} | {cdata['n']} | "
                f"{cdata['sonnet_failure_rate']:.1%} | "
                f"{cdata['crossvendor_failure_rate']:.1%} | "
                f"{cdata['classA']} |"
            )
        lines.append("")

    if "ratio_analysis" in results:
        ra = results["ratio_analysis"]
        lines.append("\n## 80x Ratio Analysis\n")
        s = ra["sonnet_judge"]
        c = ra["crossvendor_judge"]
        lines.append("| Metric | Sonnet 4.5 Judge | Cross-Vendor Judge |")
        lines.append("|--------|------------------|--------------------|")
        lines.append(
            f"| GPT failure rate | {s['gpt_failure_rate']:.3%} | {c['gpt_failure_rate']:.3%} |"
        )
        lines.append(
            f"| Opus failure rate | {s['opus_failure_rate']:.3%} | {c['opus_failure_rate']:.3%} |"
        )
        lines.append(f"| Ratio | {s['ratio']:.1f}x | {c['ratio']:.1f}x |")
        lines.append(f"\nRatio change: **{ra['ratio_change']}**")
        lines.append(f"\nEffect size (Cohen's h): {ra['effect_size_h']:.3f}")

    with open(md_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    logger.info("Markdown saved: %s", md_path)


def main():
    parser = argparse.ArgumentParser(
        description="Compare original vs cross-vendor MSTS grades"
    )
    parser.add_argument("--study", type=int, choices=[2, 3], default=None)
    parser.add_argument(
        "--results-dir",
        default=None,
        help="Directory with cross-vendor grade files (default: results/msts-crossvendor)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    crossvendor_dir = Path(args.results_dir) if args.results_dir else None
    results = compare(study_filter=args.study, crossvendor_dir=crossvendor_dir)
    print_report(results)
    save_report(results, output_dir=crossvendor_dir)


if __name__ == "__main__":
    main()
