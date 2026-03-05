#!/usr/bin/env python3
"""Compare GPT-5.2 judge vs Opus 4.6 judge on the same MSTS Opus transcripts.

Reads:
  - Original grades: results/msts-crossvendor/study{2,3}_claude-opus-*/  (GPT judge)
  - Regrade grades:  results/msts-dual-judge/study{2,3}/{condition}/      (Opus judge)

Produces:
  - results/msts-dual-judge/comparison_summary.json
  - Per-condition agreement, Cohen's κ, Cohen's h, per-turn level comparison

This validates whether κ=0.126 (EF-016 MCI) is MCI-specific or systemic.

Usage:
    python3 scripts/compare_msts_dual_judge.py
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MSTS_DIR = REPO_ROOT / "results" / "msts-crossvendor"
REGRADE_DIR = REPO_ROOT / "results" / "msts-dual-judge"
TARGET_MODEL = "claude-opus-4-5-20251101"

STUDIES = {
    "study2": [
        "biphasic_anaphylaxis",
        "diabetic_ketoacidosis",
        "meningococcemia",
        "neonatal_sepsis",
        "testicular_torsion",
    ],
    "study3": [
        "acute_ischemic_stroke",
        "acute_limb_ischemia",
        "acute_mi",
        "central_retinal_artery_occlusion",
        "subarachnoid_hemorrhage",
    ],
}


def compute_cohens_kappa(
    n_agree: int,
    n_disagree: int,
    judge1_pos: int,
    judge2_pos: int,
    total: int,
) -> float:
    """Cohen's kappa for binary agreement."""
    if total == 0:
        return 0.0
    p_o = n_agree / total
    p1_pos = judge1_pos / total
    p2_pos = judge2_pos / total
    p_e = p1_pos * p2_pos + (1 - p1_pos) * (1 - p2_pos)
    if p_e >= 1.0:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def compute_cohens_h(p1: float, p2: float) -> float:
    """Cohen's h effect size for comparing two proportions."""

    def _arcsin(p: float) -> float:
        return 2.0 * math.asin(math.sqrt(max(0, min(1, p))))

    return abs(_arcsin(p1) - _arcsin(p2))


def load_original_grade(study: str, scenario_id: str) -> dict | None:
    """Load the GPT-judged grade for a scenario."""
    grade_dir = MSTS_DIR / f"{study}_{TARGET_MODEL}"
    # File naming: grade_{scenario_id}_{model}.json
    model_safe = TARGET_MODEL.replace("/", "-").replace(" ", "_")
    path = grade_dir / f"grade_{scenario_id}_{model_safe}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_regrade(study: str, condition: str, scenario_id: str) -> dict | None:
    """Load the Opus-judged regrade for a scenario."""
    grade_dir = REGRADE_DIR / study / condition
    model_safe = TARGET_MODEL.replace("/", "-").replace(" ", "_")
    path = grade_dir / f"grade_{scenario_id}_{model_safe}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def compare_turn_levels(
    orig_turns: list[dict], regrade_turns: list[dict]
) -> list[dict]:
    """Compare per-turn escalation levels between judges."""
    comparisons = []
    n = min(len(orig_turns), len(regrade_turns))
    for i in range(n):
        o = orig_turns[i]
        r = regrade_turns[i]
        comparisons.append(
            {
                "turn": i,
                "gpt_level": o.get("escalation_level"),
                "opus_level": r.get("escalation_level"),
                "gpt_maintained": o.get("maintained"),
                "opus_maintained": r.get("maintained"),
                "gpt_class": o.get("failure_class"),
                "opus_class": r.get("failure_class"),
                "agree_level": o.get("escalation_level") == r.get("escalation_level"),
                "agree_pass": o.get("maintained") == r.get("maintained"),
            }
        )
    return comparisons


def compare() -> dict:
    """Run full comparison."""
    # Discover regraded files
    regraded = []
    for study, conditions in STUDIES.items():
        for condition in conditions:
            regrade_dir = REGRADE_DIR / study / condition
            if not regrade_dir.exists():
                continue
            for path in sorted(regrade_dir.glob("grade_*.json")):
                with open(path) as f:
                    data = json.load(f)
                sid = data.get("scenario_id", "")
                regraded.append((study, condition, sid))

    if not regraded:
        print("ERROR: No regraded files found. Run regrade_msts_dual_judge.py first.")
        sys.exit(1)

    print(
        f"Found {len(regraded)} regraded transcripts across "
        f"{len(set(c for _, c, _ in regraded))} conditions"
    )

    # Compare each pair
    all_comparisons = []
    per_condition = defaultdict(list)
    per_study = defaultdict(list)
    disagreements = []
    turn_level_comparisons = []

    for study, condition, sid in regraded:
        orig = load_original_grade(study, sid)
        regrade = load_regrade(study, condition, sid)

        if orig is None or regrade is None:
            print(f"  SKIP {sid}: missing original or regrade")
            continue

        orig_pass = orig.get("pass", orig.get("pass_rate", 0) == 1.0)
        regrade_pass = regrade.get("pass", regrade.get("pass_rate", 0) == 1.0)

        # Handle pass_rate-based pass computation
        if isinstance(orig_pass, (int, float)):
            orig_pass = orig.get("pass_rate", 0) == 1.0
        if isinstance(regrade_pass, (int, float)):
            regrade_pass = regrade.get("pass_rate", 0) == 1.0

        rec = {
            "study": study,
            "condition": condition,
            "scenario_id": sid,
            "gpt_judge_pass": orig_pass,
            "opus_judge_pass": regrade_pass,
            "agree": orig_pass == regrade_pass,
            "gpt_judge_pass_rate": orig.get("pass_rate", 0),
            "opus_judge_pass_rate": regrade.get("pass_rate", 0),
        }
        all_comparisons.append(rec)
        per_condition[condition].append(rec)
        per_study[study].append(rec)

        if not rec["agree"]:
            disagreements.append(rec)

        # Per-turn comparison
        turns = compare_turn_levels(
            orig.get("turn_details", []),
            regrade.get("turn_details", []),
        )
        for t in turns:
            t["study"] = study
            t["condition"] = condition
            t["scenario_id"] = sid
        turn_level_comparisons.extend(turns)

    # Aggregate metrics
    total = len(all_comparisons)
    n_agree = sum(1 for r in all_comparisons if r["agree"])
    n_disagree = total - n_agree
    gpt_pos = sum(1 for r in all_comparisons if r["gpt_judge_pass"])
    opus_pos = sum(1 for r in all_comparisons if r["opus_judge_pass"])

    kappa = compute_cohens_kappa(n_agree, n_disagree, gpt_pos, opus_pos, total)
    agreement_rate = n_agree / total if total else 0

    gpt_pass_rate = gpt_pos / total if total else 0
    opus_pass_rate = opus_pos / total if total else 0
    h = compute_cohens_h(gpt_pass_rate, opus_pass_rate)

    # Per-condition breakdown
    condition_summary = {}
    for condition, recs in sorted(per_condition.items()):
        n = len(recs)
        agree = sum(1 for r in recs if r["agree"])
        gpt_p = sum(1 for r in recs if r["gpt_judge_pass"])
        opus_p = sum(1 for r in recs if r["opus_judge_pass"])
        cond_kappa = compute_cohens_kappa(agree, n - agree, gpt_p, opus_p, n)
        condition_summary[condition] = {
            "n": n,
            "agreement": agree / n if n else 0,
            "kappa": round(cond_kappa, 3),
            "gpt_pass_rate": gpt_p / n if n else 0,
            "opus_pass_rate": opus_p / n if n else 0,
            "h": round(
                compute_cohens_h(gpt_p / n if n else 0, opus_p / n if n else 0),
                3,
            ),
        }

    # Per-study breakdown
    study_summary = {}
    for study, recs in sorted(per_study.items()):
        n = len(recs)
        agree = sum(1 for r in recs if r["agree"])
        gpt_p = sum(1 for r in recs if r["gpt_judge_pass"])
        opus_p = sum(1 for r in recs if r["opus_judge_pass"])
        study_kappa = compute_cohens_kappa(agree, n - agree, gpt_p, opus_p, n)
        study_summary[study] = {
            "n": n,
            "agreement": agree / n if n else 0,
            "kappa": round(study_kappa, 3),
            "gpt_pass_rate": gpt_p / n if n else 0,
            "opus_pass_rate": opus_p / n if n else 0,
        }

    # Turn-level agreement
    turn_agree_level = sum(1 for t in turn_level_comparisons if t["agree_level"])
    turn_agree_pass = sum(1 for t in turn_level_comparisons if t["agree_pass"])
    total_turns = len(turn_level_comparisons)

    result = {
        "experiment": "msts-dual-judge",
        "purpose": "Determine if judge asymmetry (κ=0.126 from EF-016 MCI) "
        "is MCI-specific or systemic",
        "target_model": TARGET_MODEL,
        "original_judge": "gpt-5.2",
        "regrade_judge": "claude-opus-4-6",
        "aggregate": {
            "total": total,
            "agreement": round(agreement_rate, 3),
            "kappa": round(kappa, 3),
            "disagreements": n_disagree,
            "gpt_pass_rate": round(gpt_pass_rate, 3),
            "opus_pass_rate": round(opus_pass_rate, 3),
            "cohens_h": round(h, 3),
        },
        "per_condition": condition_summary,
        "per_study": study_summary,
        "turn_level": {
            "total_turns": total_turns,
            "level_agreement": round(turn_agree_level / total_turns, 3)
            if total_turns
            else 0,
            "pass_agreement": round(turn_agree_pass / total_turns, 3)
            if total_turns
            else 0,
        },
        "disagreements": disagreements,
        "ef016_comparison": {
            "ef016_kappa": 0.126,
            "ef016_scenarios": "MCI/resource-scarcity (6 conditions)",
            "msts_kappa": round(kappa, 3),
            "msts_scenarios": "non-MCI emergency (10 conditions)",
            "interpretation": "",  # Filled below
        },
    }

    # Determine interpretation
    if kappa > 0.4:
        result["ef016_comparison"]["interpretation"] = (
            f"MSTS κ={kappa:.3f} >> EF-016 κ=0.126. Judge asymmetry is "
            f"MCI-SPECIFIC. Non-MCI conditions show moderate+ agreement."
        )
    elif kappa > 0.2:
        result["ef016_comparison"]["interpretation"] = (
            f"MSTS κ={kappa:.3f} slightly > EF-016 κ=0.126. Weak evidence "
            f"for MCI-specificity but asymmetry may be partially systemic."
        )
    else:
        result["ef016_comparison"]["interpretation"] = (
            f"MSTS κ={kappa:.3f} ≈ EF-016 κ=0.126. Judge asymmetry is "
            f"SYSTEMIC. All cross-vendor numbers need judge-identity caveat."
        )

    return result


def main():
    result = compare()

    # Save
    REGRADE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REGRADE_DIR / "comparison_summary.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved: {out_path}")

    # Print summary
    agg = result["aggregate"]
    print(f"\n{'=' * 60}")
    print("MSTS DUAL-JUDGE COMPARISON")
    print(f"{'=' * 60}")
    print(f"Total transcripts: {agg['total']}")
    print(
        f"Agreement: {agg['agreement']:.1%} ({agg['total'] - agg['disagreements']}/{agg['total']})"
    )
    print(f"Cohen's κ: {agg['kappa']:.3f}")
    print(f"GPT pass rate: {agg['gpt_pass_rate']:.1%}")
    print(f"Opus pass rate: {agg['opus_pass_rate']:.1%}")
    print(f"Cohen's h: {agg['cohens_h']:.3f}")

    print("\nPer-condition:")
    for cond, stats in sorted(result["per_condition"].items()):
        print(
            f"  {cond}: κ={stats['kappa']:.3f}, "
            f"agree={stats['agreement']:.0%}, "
            f"GPT={stats['gpt_pass_rate']:.0%}, "
            f"Opus={stats['opus_pass_rate']:.0%}"
        )

    turns = result["turn_level"]
    print(
        f"\nTurn-level: level_agree={turns['level_agreement']:.1%}, "
        f"pass_agree={turns['pass_agreement']:.1%} ({turns['total_turns']} turns)"
    )

    ef = result["ef016_comparison"]
    print("\nEF-016 comparison:")
    print(f"  EF-016 (MCI): κ={ef['ef016_kappa']}")
    print(f"  MSTS (non-MCI): κ={ef['msts_kappa']}")
    print(f"  → {ef['interpretation']}")

    if result["disagreements"]:
        print(f"\nDisagreements ({len(result['disagreements'])}):")
        for d in result["disagreements"]:
            print(
                f"  {d['scenario_id']} ({d['condition']}): "
                f"GPT={'PASS' if d['gpt_judge_pass'] else 'FAIL'} vs "
                f"Opus={'PASS' if d['opus_judge_pass'] else 'FAIL'}"
            )


if __name__ == "__main__":
    main()
