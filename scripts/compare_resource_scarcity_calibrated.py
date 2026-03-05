#!/usr/bin/env python3
"""Compare calibrated Opus 4.6 vs calibrated GPT-5.2 judge grades.

Both judges used the calibrated prompt (Level 2/1 boundary + MCI responder).
This gives the true calibrated inter-judge κ, resolving the κ paradox from
comparing calibrated GPT grades against uncalibrated Opus grades.

Compares: grades-opus-calibrated/ vs grades-gpt-judge/

Also computes delta from original uncalibrated grades/ for context.

Output: results/resource-scarcity-crossvendor/judge_comparison_calibrated.json

Usage:
    python3 scripts/compare_resource_scarcity_calibrated.py
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lostbench.grader import GradeResult

logger = logging.getLogger("compare_resource_scarcity_calibrated")

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSVENDOR_DIR = REPO_ROOT / "results" / "resource-scarcity-crossvendor"

MODELS = ["gpt-5.2", "gemini-3.1-pro", "grok-4-fast"]
ARMS = ["baseline", "preamble"]

EF016_EXCLUDE = {"MTR-052"}


def compute_cohens_kappa(
    agree_pass: int,
    agree_fail: int,
    judge1_only_fail: int,
    judge2_only_fail: int,
) -> float:
    """Compute Cohen's kappa for inter-rater agreement."""
    n = agree_pass + agree_fail + judge1_only_fail + judge2_only_fail
    if n == 0:
        return 0.0
    observed = (agree_pass + agree_fail) / n
    p1_fail = (agree_fail + judge1_only_fail) / n
    p2_fail = (agree_fail + judge2_only_fail) / n
    p1_pass = 1 - p1_fail
    p2_pass = 1 - p2_fail
    expected = (p1_fail * p2_fail) + (p1_pass * p2_pass)
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def compute_cohens_h(p1: float, p2: float) -> float:
    """Compute Cohen's h effect size for two proportions."""
    phi1 = 2 * math.asin(math.sqrt(max(0, min(1, p1))))
    phi2 = 2 * math.asin(math.sqrt(max(0, min(1, p2))))
    return abs(phi2 - phi1)


def load_grades(model: str, arm: str, judge_subdir: str) -> dict[str, GradeResult]:
    """Load grade files for a model/arm/judge combination."""
    grade_dir = CROSSVENDOR_DIR / model / judge_subdir / arm
    grades = {}
    if not grade_dir.exists():
        logger.warning("Grade dir not found: %s", grade_dir)
        return grades
    for path in sorted(grade_dir.glob("grade_*.json")):
        grade = GradeResult.load(path)
        grades[grade.scenario_id] = grade
    return grades


def compare_turn_levels(opus_grade: GradeResult, gpt_grade: GradeResult) -> dict:
    """Compare per-turn escalation levels between two judge grades."""
    opus_turns = opus_grade.turn_details
    gpt_turns = gpt_grade.turn_details

    if len(opus_turns) != len(gpt_turns):
        return {"error": f"turn count mismatch: {len(opus_turns)} vs {len(gpt_turns)}"}

    agreements = 0
    disagreements = 0
    level_diffs = []

    for ot, gt in zip(opus_turns, gpt_turns):
        ol = ot.get("escalation_level", -1)
        gl = gt.get("escalation_level", -1)
        if ol == gl:
            agreements += 1
        else:
            disagreements += 1
        level_diffs.append(gl - ol)

    n = len(opus_turns)
    return {
        "n_turns": n,
        "level_agreements": agreements,
        "level_disagreements": disagreements,
        "level_agreement_rate": round(agreements / n, 3) if n else 0,
        "mean_level_diff": round(sum(level_diffs) / n, 3) if n else 0,
    }


def compare_pair(
    opus_subdir: str,
    gpt_subdir: str,
    label: str,
) -> tuple[dict, list[dict]]:
    """Compare two sets of judge grades. Returns (aggregate, disagreements)."""
    total_ap = 0
    total_af = 0
    total_opus_only = 0
    total_gpt_only = 0
    all_disagreements = []
    model_results = {}

    for model in MODELS:
        model_result = {"arms": {}}
        for arm in ARMS:
            opus_grades = load_grades(model, arm, opus_subdir)
            gpt_grades = load_grades(model, arm, gpt_subdir)

            if not opus_grades or not gpt_grades:
                continue

            common_sids = sorted(set(opus_grades.keys()) & set(gpt_grades.keys()))
            ap = af = opus_only = gpt_only = 0
            per_scenario = {}

            for sid in common_sids:
                og = opus_grades[sid]
                gg = gpt_grades[sid]
                op = og.passed
                gp = gg.passed

                if op and gp:
                    ap += 1
                elif not op and not gp:
                    af += 1
                elif not op and gp:
                    opus_only += 1
                else:
                    gpt_only += 1

                if op != gp:
                    all_disagreements.append(
                        {
                            "model": model,
                            "arm": arm,
                            "scenario_id": sid,
                            "opus_pass": op,
                            "gpt_pass": gp,
                            "opus_pass_rate": og.pass_rate,
                            "gpt_pass_rate": gg.pass_rate,
                            "opus_classA": og.classA,
                            "gpt_classA": gg.classA,
                        }
                    )

                turn_cmp = compare_turn_levels(og, gg)
                per_scenario[sid] = {
                    "opus_pass": op,
                    "gpt_pass": gp,
                    "opus_pass_rate": og.pass_rate,
                    "gpt_pass_rate": gg.pass_rate,
                    "turn_comparison": turn_cmp,
                }

            n = len(common_sids)
            agr_rate = (ap + af) / n if n else 0
            kappa = compute_cohens_kappa(ap, af, opus_only, gpt_only)

            model_result["arms"][arm] = {
                "n_scenarios": n,
                "per_scenario": per_scenario,
                "agreement_matrix": {
                    "agree_pass": ap,
                    "agree_fail": af,
                    "opus_only_fail": opus_only,
                    "gpt_only_fail": gpt_only,
                },
                "agreement_rate": round(agr_rate, 3),
                "cohens_kappa": round(kappa, 3),
            }

            total_ap += ap
            total_af += af
            total_opus_only += opus_only
            total_gpt_only += gpt_only

        model_results[model] = model_result

    total_n = total_ap + total_af + total_opus_only + total_gpt_only
    agg_rate = (total_ap + total_af) / total_n if total_n else 0
    agg_kappa = compute_cohens_kappa(
        total_ap, total_af, total_opus_only, total_gpt_only
    )

    aggregate = {
        "label": label,
        "opus_subdir": opus_subdir,
        "gpt_subdir": gpt_subdir,
        "n_total": total_n,
        "agreement_matrix": {
            "agree_pass": total_ap,
            "agree_fail": total_af,
            "opus_only_fail": total_opus_only,
            "gpt_only_fail": total_gpt_only,
        },
        "agreement_rate": round(agg_rate, 3),
        "cohens_kappa": round(agg_kappa, 3),
        "models": model_results,
    }

    return aggregate, all_disagreements


def compare() -> dict:
    """Run comparison: calibrated Opus vs calibrated GPT."""
    # Primary: both calibrated
    calibrated, cal_disagreements = compare_pair(
        "grades-opus-calibrated",
        "grades-gpt-judge",
        "Both calibrated (true calibrated κ)",
    )

    # Reference: original uncalibrated Opus vs calibrated GPT (prior result)
    uncalibrated, uncal_disagreements = compare_pair(
        "grades",
        "grades-gpt-judge",
        "Uncalibrated Opus vs calibrated GPT (prior result)",
    )

    # Opus calibration delta: original vs calibrated Opus
    opus_delta, opus_disagreements = compare_pair(
        "grades",
        "grades-opus-calibrated",
        "Opus uncalibrated vs Opus calibrated (prompt effect)",
    )

    return {
        "calibrated_comparison": calibrated,
        "calibrated_disagreements": cal_disagreements,
        "uncalibrated_reference": uncalibrated,
        "uncalibrated_disagreements": uncal_disagreements,
        "opus_prompt_delta": opus_delta,
        "opus_prompt_disagreements": opus_disagreements,
        "kappa_progression": {
            "stage_0_uncalibrated": 0.126,
            "stage_1_level_boundary_gpt_only": 0.344,
            "stage_2_mci_gpt_only": 0.191,
            "stage_3_both_calibrated": calibrated["cohens_kappa"],
        },
    }


def print_report(results: dict) -> None:
    """Print human-readable report."""
    print("\n" + "=" * 80)
    print("RESOURCE SCARCITY CROSSVENDOR — CALIBRATED JUDGE COMPARISON")
    print("=" * 80)

    # Primary result
    cal = results["calibrated_comparison"]
    print(f"\n--- {cal['label']} ---")
    print(f"  N={cal['n_total']}")
    print(f"  Agreement: {cal['agreement_rate']:.1%}")
    print(f"  Cohen's κ: {cal['cohens_kappa']:.3f}")
    agr = cal["agreement_matrix"]
    print(
        f"  Matrix: pass={agr['agree_pass']}, fail={agr['agree_fail']}, "
        f"opus-only={agr['opus_only_fail']}, gpt-only={agr['gpt_only_fail']}"
    )

    # Reference
    uncal = results["uncalibrated_reference"]
    print(f"\n--- {uncal['label']} ---")
    print(f"  Agreement: {uncal['agreement_rate']:.1%}")
    print(f"  Cohen's κ: {uncal['cohens_kappa']:.3f}")
    agr = uncal["agreement_matrix"]
    print(
        f"  Matrix: pass={agr['agree_pass']}, fail={agr['agree_fail']}, "
        f"opus-only={agr['opus_only_fail']}, gpt-only={agr['gpt_only_fail']}"
    )

    # Opus delta
    delta = results["opus_prompt_delta"]
    print(f"\n--- {delta['label']} ---")
    print(f"  Agreement: {delta['agreement_rate']:.1%}")
    print(f"  Cohen's κ: {delta['cohens_kappa']:.3f}")
    agr = delta["agreement_matrix"]
    print(
        f"  Matrix: same={agr['agree_pass'] + agr['agree_fail']}, "
        f"changed: uncal-only-fail={agr['opus_only_fail']}, cal-only-fail={agr['gpt_only_fail']}"
    )

    # κ progression
    print(f"\n{'=' * 60}")
    print("κ PROGRESSION")
    prog = results["kappa_progression"]
    for stage, k in prog.items():
        label = stage.replace("_", " ").title()
        print(f"  {label}: {k:.3f}")

    # Calibrated disagreements
    cal_dis = results["calibrated_disagreements"]
    if cal_dis:
        print(f"\n{'─' * 60}")
        print(f"CALIBRATED DISAGREEMENTS ({len(cal_dis)}):")
        for d in cal_dis:
            opus_str = "PASS" if d["opus_pass"] else "FAIL"
            gpt_str = "PASS" if d["gpt_pass"] else "FAIL"
            print(
                f"  {d['model']}/{d['arm']}/{d['scenario_id']}: "
                f"Opus={opus_str}({d['opus_pass_rate']:.0%}) "
                f"GPT={gpt_str}({d['gpt_pass_rate']:.0%})"
            )
    else:
        print("\n  No calibrated disagreements — perfect inter-judge agreement!")

    # Kappa interpretation
    k = cal["cohens_kappa"]
    if k >= 0.8:
        interp = "Almost perfect"
    elif k >= 0.6:
        interp = "Substantial"
    elif k >= 0.4:
        interp = "Moderate"
    elif k >= 0.2:
        interp = "Fair"
    else:
        interp = "Slight/poor"
    print(f"\n  Calibrated κ interpretation: {interp} agreement")
    if k >= 0.6:
        print("  ✓ κ ≥ 0.6 — cross-vendor numbers are judge-independent")
    else:
        print("  ⚠ κ < 0.6 — cross-vendor numbers remain judge-dependent")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    results = compare()
    print_report(results)

    output_path = CROSSVENDOR_DIR / "judge_comparison_calibrated.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Saved: %s", output_path)


if __name__ == "__main__":
    main()
