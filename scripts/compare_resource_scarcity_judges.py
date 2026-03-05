#!/usr/bin/env python3
"""Compare Opus 4.6 vs GPT-5.2 judge grades for resource-scarcity-crossvendor.

Loads original Opus-judged grades (grades/) and GPT-regraded grades (grades-gpt-judge/)
for all 3 non-Anthropic models. Computes:
  - Per-scenario pass rate under each judge
  - Per-turn escalation level agreement (ordinal Cohen's kappa)
  - Binary pass/fail agreement matrix per model
  - Scenarios where judges disagree on pass/fail
  - Cohen's h effect size for pass rate differences

Output: results/resource-scarcity-crossvendor/judge_comparison.json

Usage:
    python3 scripts/compare_resource_scarcity_judges.py
"""

from __future__ import annotations

import json
import logging
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lostbench.grader import GradeResult

logger = logging.getLogger("compare_resource_scarcity_judges")

REPO_ROOT = Path(__file__).resolve().parent.parent
CROSSVENDOR_DIR = REPO_ROOT / "results" / "resource-scarcity-crossvendor"

MODELS = ["gpt-5.2", "gemini-3.1-pro", "grok-4-fast"]
ARMS = ["baseline", "preamble"]

# EF-016 excludes MTR-052 (triage advisory)
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
    failure_class_agree = 0
    failure_class_disagree = 0

    for ot, gt in zip(opus_turns, gpt_turns):
        ol = ot.get("escalation_level", -1)
        gl = gt.get("escalation_level", -1)
        if ol == gl:
            agreements += 1
        else:
            disagreements += 1
        level_diffs.append(gl - ol)  # positive = GPT judge grades higher

        ofc = ot.get("failure_class")
        gfc = gt.get("failure_class")
        if ofc == gfc:
            failure_class_agree += 1
        else:
            failure_class_disagree += 1

    n = len(opus_turns)
    return {
        "n_turns": n,
        "level_agreements": agreements,
        "level_disagreements": disagreements,
        "level_agreement_rate": round(agreements / n, 3) if n else 0,
        "mean_level_diff": round(sum(level_diffs) / n, 3) if n else 0,
        "failure_class_agreements": failure_class_agree,
        "failure_class_disagreements": failure_class_disagree,
    }


def compare() -> dict:
    """Run full judge comparison analysis."""
    results = {
        "opus_judge": "claude-opus-4-6",
        "gpt_judge": "gpt-5.2",
        "models": {},
        "aggregate": {},
    }

    # Global counters
    total_agree_pass = 0
    total_agree_fail = 0
    total_opus_only_fail = 0
    total_gpt_only_fail = 0
    all_disagreements = []

    for model in MODELS:
        model_result = {"arms": {}, "ef016": {}}

        for arm in ARMS:
            opus_grades = load_grades(model, arm, "grades")
            gpt_grades = load_grades(model, arm, "grades-gpt-judge")

            if not opus_grades or not gpt_grades:
                logger.warning("Missing grades for %s/%s", model, arm)
                continue

            # Match scenarios present in both
            common_sids = sorted(set(opus_grades.keys()) & set(gpt_grades.keys()))
            logger.info(
                "%s/%s: %d matched scenarios (%d opus, %d gpt)",
                model,
                arm,
                len(common_sids),
                len(opus_grades),
                len(gpt_grades),
            )

            per_scenario = {}
            arm_agree_pass = 0
            arm_agree_fail = 0
            arm_opus_only_fail = 0
            arm_gpt_only_fail = 0

            for sid in common_sids:
                og = opus_grades[sid]
                gg = gpt_grades[sid]

                opus_pass = og.passed
                gpt_pass = gg.passed

                if opus_pass and gpt_pass:
                    arm_agree_pass += 1
                elif not opus_pass and not gpt_pass:
                    arm_agree_fail += 1
                elif not opus_pass and gpt_pass:
                    arm_opus_only_fail += 1
                else:
                    arm_gpt_only_fail += 1

                # Track disagreements
                if opus_pass != gpt_pass:
                    all_disagreements.append(
                        {
                            "model": model,
                            "arm": arm,
                            "scenario_id": sid,
                            "opus_pass": opus_pass,
                            "gpt_pass": gpt_pass,
                            "opus_pass_rate": og.pass_rate,
                            "gpt_pass_rate": gg.pass_rate,
                            "opus_classA": og.classA,
                            "gpt_classA": gg.classA,
                        }
                    )

                turn_comparison = compare_turn_levels(og, gg)

                per_scenario[sid] = {
                    "opus_pass": opus_pass,
                    "gpt_pass": gpt_pass,
                    "opus_pass_rate": og.pass_rate,
                    "gpt_pass_rate": gg.pass_rate,
                    "pass_rate_diff": round(gg.pass_rate - og.pass_rate, 3),
                    "opus_classA": og.classA,
                    "gpt_classA": gg.classA,
                    "opus_classD": og.classD,
                    "gpt_classD": gg.classD,
                    "turn_comparison": turn_comparison,
                }

            n = len(common_sids)
            agreement_rate = (arm_agree_pass + arm_agree_fail) / n if n else 0
            kappa = compute_cohens_kappa(
                arm_agree_pass, arm_agree_fail, arm_opus_only_fail, arm_gpt_only_fail
            )

            opus_pass_rate = (arm_agree_pass + arm_gpt_only_fail) / n if n else 0
            gpt_pass_rate = (arm_agree_pass + arm_opus_only_fail) / n if n else 0
            h = compute_cohens_h(opus_pass_rate, gpt_pass_rate)

            model_result["arms"][arm] = {
                "n_scenarios": n,
                "per_scenario": per_scenario,
                "agreement_matrix": {
                    "agree_pass": arm_agree_pass,
                    "agree_fail": arm_agree_fail,
                    "opus_only_fail": arm_opus_only_fail,
                    "gpt_only_fail": arm_gpt_only_fail,
                },
                "agreement_rate": round(agreement_rate, 3),
                "cohens_kappa": round(kappa, 3),
                "opus_pass_rate": round(opus_pass_rate, 3),
                "gpt_pass_rate": round(gpt_pass_rate, 3),
                "cohens_h": round(h, 3),
            }

            total_agree_pass += arm_agree_pass
            total_agree_fail += arm_agree_fail
            total_opus_only_fail += arm_opus_only_fail
            total_gpt_only_fail += arm_gpt_only_fail

        # EF-016 rates (excluding MTR-052)
        for arm in ARMS:
            if arm not in model_result["arms"]:
                continue
            arm_data = model_result["arms"][arm]
            ef016_scenarios = {
                sid: data
                for sid, data in arm_data["per_scenario"].items()
                if sid not in EF016_EXCLUDE
            }
            if ef016_scenarios:
                n_ef = len(ef016_scenarios)
                opus_ef_pass = sum(
                    1 for d in ef016_scenarios.values() if d["opus_pass"]
                )
                gpt_ef_pass = sum(1 for d in ef016_scenarios.values() if d["gpt_pass"])
                model_result["ef016"][arm] = {
                    "n_scenarios": n_ef,
                    "opus_pass_rate": round(opus_ef_pass / n_ef, 3),
                    "gpt_pass_rate": round(gpt_ef_pass / n_ef, 3),
                    "cohens_h": round(
                        compute_cohens_h(opus_ef_pass / n_ef, gpt_ef_pass / n_ef), 3
                    ),
                }

        results["models"][model] = model_result

    # Aggregate
    total_n = (
        total_agree_pass + total_agree_fail + total_opus_only_fail + total_gpt_only_fail
    )
    agg_agreement = (total_agree_pass + total_agree_fail) / total_n if total_n else 0
    agg_kappa = compute_cohens_kappa(
        total_agree_pass, total_agree_fail, total_opus_only_fail, total_gpt_only_fail
    )

    results["aggregate"] = {
        "n_total": total_n,
        "agreement_matrix": {
            "agree_pass": total_agree_pass,
            "agree_fail": total_agree_fail,
            "opus_only_fail": total_opus_only_fail,
            "gpt_only_fail": total_gpt_only_fail,
        },
        "agreement_rate": round(agg_agreement, 3),
        "cohens_kappa": round(agg_kappa, 3),
    }

    results["disagreements"] = all_disagreements

    return results


def print_report(results: dict) -> None:
    """Print human-readable comparison report."""
    print("\n" + "=" * 80)
    print("RESOURCE SCARCITY CROSSVENDOR — JUDGE COMPARISON REPORT")
    print(f"Opus judge: {results['opus_judge']}  |  GPT judge: {results['gpt_judge']}")
    print("=" * 80)

    for model, data in sorted(results["models"].items()):
        print(f"\n{'─' * 60}")
        print(f"Model: {model}")

        for arm in ARMS:
            if arm not in data["arms"]:
                continue
            ad = data["arms"][arm]
            print(f"\n  {arm} (N={ad['n_scenarios']}):")
            print(f"    Opus pass rate: {ad['opus_pass_rate']:.1%}")
            print(f"    GPT pass rate:  {ad['gpt_pass_rate']:.1%}")
            print(f"    Agreement:      {ad['agreement_rate']:.1%}")
            print(f"    Cohen's κ:      {ad['cohens_kappa']:.3f}")
            print(f"    Cohen's h:      {ad['cohens_h']:.3f}")

            agr = ad["agreement_matrix"]
            print(
                f"    Matrix: pass={agr['agree_pass']}, fail={agr['agree_fail']}, "
                f"opus-only={agr['opus_only_fail']}, gpt-only={agr['gpt_only_fail']}"
            )

        if data.get("ef016"):
            print("\n  EF-016 (MTR-052 excluded):")
            for arm, ef in data["ef016"].items():
                print(
                    f"    {arm}: opus={ef['opus_pass_rate']:.1%} "
                    f"gpt={ef['gpt_pass_rate']:.1%} h={ef['cohens_h']:.3f}"
                )

    # Aggregate
    agg = results["aggregate"]
    print(f"\n{'=' * 60}")
    print(f"AGGREGATE (N={agg['n_total']})")
    print(f"  Agreement rate: {agg['agreement_rate']:.1%}")
    print(f"  Cohen's κ: {agg['cohens_kappa']:.3f}")
    agr = agg["agreement_matrix"]
    print(
        f"  Matrix: pass={agr['agree_pass']}, fail={agr['agree_fail']}, "
        f"opus-only={agr['opus_only_fail']}, gpt-only={agr['gpt_only_fail']}"
    )

    # Disagreements
    if results["disagreements"]:
        print(f"\n{'─' * 60}")
        print(f"DISAGREEMENTS ({len(results['disagreements'])} scenarios):")
        for d in results["disagreements"]:
            opus_str = "PASS" if d["opus_pass"] else "FAIL"
            gpt_str = "PASS" if d["gpt_pass"] else "FAIL"
            print(
                f"  {d['model']}/{d['arm']}/{d['scenario_id']}: "
                f"Opus={opus_str}({d['opus_pass_rate']:.0%}) "
                f"GPT={gpt_str}({d['gpt_pass_rate']:.0%}) "
                f"classA: {d['opus_classA']}→{d['gpt_classA']}"
            )

    # Kappa interpretation
    k = agg["cohens_kappa"]
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
    print(f"\n  κ interpretation: {interp} agreement")
    if k < 0.6:
        print("  ⚠ κ < 0.6 — cross-vendor numbers are judge-dependent")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    results = compare()
    print_report(results)

    # Save JSON
    output_path = CROSSVENDOR_DIR / "judge_comparison.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Saved: %s", output_path)


if __name__ == "__main__":
    main()
