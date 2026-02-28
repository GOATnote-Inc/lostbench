#!/usr/bin/env python3
"""Find specific MSTS trajectories for forensic analysis.

Categorizes study2 trajectories into 4 buckets based on
agreement/disagreement between original Sonnet 4.5 grading and CEIS
cross-vendor grading. Also finds a study3 example.

Focuses on Opus 4.5, falls back to GPT-5.2 for empty buckets.
"""

import json
from pathlib import Path

BASE = Path("/Users/kiteboard/lostbench/results")

MODELS = [
    "claude-opus-4-5-20251101",
    "gpt-5.2",
]


def load_json(path):
    with open(path) as f:
        return json.load(f)


def scan_study2(model):
    """Iterate through study2 trajectories for a model, return 4 buckets."""
    import_dir = BASE / f"msts-import/study2_{model}"
    grade_dir = BASE / f"msts-crossvendor/study2_{model}"

    buckets = {
        "agree_pass": [],
        "sonnet_pass_ceis_fail": [],
        "sonnet_fail_ceis_pass": [],
        "agree_fail": [],
    }

    if not import_dir.exists() or not grade_dir.exists():
        return buckets

    for cf in sorted(import_dir.glob("challenge_*.json")):
        scenario_id = cf.name.replace("challenge_", "").replace(f"_{model}.json", "")
        gf = grade_dir / f"grade_{scenario_id}_{model}.json"

        if not gf.exists():
            continue

        challenge = load_json(cf)
        grade = load_json(gf)

        orig_grading = challenge.get("metadata", {}).get("original_grading", {})
        hard_failure = orig_grading.get("hard_failure", {})
        sonnet_detected = hard_failure.get("detected")
        if sonnet_detected is None:
            continue

        sonnet_pass = not sonnet_detected
        ceis_pass = grade.get("pass")
        if ceis_pass is None:
            continue

        condition = challenge.get("condition", grade.get("condition", "unknown"))
        classification = orig_grading.get("classification", "unknown")

        entry = {
            "scenario_id": scenario_id,
            "condition": condition,
            "model": model,
            "original_classification": classification,
            "sonnet_detected_failure": sonnet_detected,
            "ceis_pass": ceis_pass,
            "classA": grade.get("classA", 0),
            "classB": grade.get("classB", 0),
            "classC": grade.get("classC", 0),
            "classD": grade.get("classD", 0),
        }

        if sonnet_pass and ceis_pass:
            buckets["agree_pass"].append(entry)
        elif sonnet_pass and not ceis_pass:
            buckets["sonnet_pass_ceis_fail"].append(entry)
        elif not sonnet_pass and ceis_pass:
            buckets["sonnet_fail_ceis_pass"].append(entry)
        else:
            buckets["agree_fail"].append(entry)

    return buckets


def scan_study3(model):
    """Find study3 trajectories that fail under CEIS."""
    import_dir = BASE / f"msts-import/study3_{model}"
    grade_dir = BASE / f"msts-crossvendor/study3_{model}"

    results = []
    if not import_dir.exists() or not grade_dir.exists():
        return results

    for cf in sorted(import_dir.glob("challenge_*.json")):
        scenario_id = cf.name.replace("challenge_", "").replace(f"_{model}.json", "")
        gf = grade_dir / f"grade_{scenario_id}_{model}.json"
        if not gf.exists():
            continue

        challenge = load_json(cf)
        grade = load_json(gf)

        ceis_pass = grade.get("pass", False)
        condition = challenge.get("condition", grade.get("condition", "unknown"))
        orig_grading = challenge.get("metadata", {}).get("original_grading", {})
        classification = orig_grading.get("classification", "unknown")

        entry = {
            "scenario_id": scenario_id,
            "condition": condition,
            "model": model,
            "original_classification": classification,
            "ceis_pass": ceis_pass,
            "classA": grade.get("classA", 0),
            "classB": grade.get("classB", 0),
            "classC": grade.get("classC", 0),
            "classD": grade.get("classD", 0),
        }
        results.append(entry)

    return results


def print_entry(label, entry):
    print(f"\n{'='*70}")
    print(f"  BUCKET: {label}")
    print(f"{'='*70}")
    print(f"  scenario_id:            {entry['scenario_id']}")
    print(f"  condition:              {entry['condition']}")
    print(f"  model:                  {entry['model']}")
    print(f"  original classification: {entry['original_classification']}")
    if "sonnet_detected_failure" in entry:
        sonnet_str = "PASS" if not entry["sonnet_detected_failure"] else "FAIL"
        print(f"  Sonnet 4.5 grading:     {sonnet_str} (hard_failure.detected={entry['sonnet_detected_failure']})")
    print(f"  CEIS grade:             {'PASS' if entry['ceis_pass'] else 'FAIL'}")
    print(f"  Class A failures:       {entry['classA']}")
    print(f"  Class B failures:       {entry['classB']}")
    print(f"  Class C failures:       {entry['classC']}")
    print(f"  Class D failures:       {entry['classD']}")


def pick_best(bucket, prefer_classA=False):
    """Pick the best example from a bucket."""
    if not bucket:
        return None
    if prefer_classA:
        with_A = [e for e in bucket if e["classA"] > 0]
        if with_A:
            return with_A[0]
    # For agree-pass, prefer clean (no class A)
    clean = [e for e in bucket if e["classA"] == 0]
    if clean:
        return clean[0]
    return bucket[0]


def main():
    print("=" * 70)
    print("  MSTS Forensic Trajectory Finder")
    print("=" * 70)

    # Scan all models for study2
    all_buckets = {}
    for model in MODELS:
        buckets = scan_study2(model)
        all_buckets[model] = buckets

        total = sum(len(v) for v in buckets.values())
        print(f"\n  Study 2 [{model}]: {total} trajectories")
        print(f"    Agree-pass   (Sonnet PASS + CEIS PASS):  {len(buckets['agree_pass']):>3}")
        print(f"    Sonnet-pass  (Sonnet PASS + CEIS FAIL):  {len(buckets['sonnet_pass_ceis_fail']):>3}")
        print(f"    Sonnet-fail  (Sonnet FAIL + CEIS PASS):  {len(buckets['sonnet_fail_ceis_pass']):>3}")
        print(f"    Agree-fail   (Sonnet FAIL + CEIS FAIL):  {len(buckets['agree_fail']):>3}")

    # Pick one example per bucket, preferring Opus 4.5
    chosen = {}
    OPUS = "claude-opus-4-5-20251101"
    GPT = "gpt-5.2"

    # Bucket 1: agree-pass (prefer Opus)
    for model in [OPUS, GPT]:
        cand = pick_best(all_buckets[model]["agree_pass"])
        if cand:
            chosen["1_agree_pass"] = cand
            break

    # Bucket 2: sonnet-pass + CEIS-fail (prefer Opus, fall back to GPT)
    for model in [OPUS, GPT]:
        cand = pick_best(all_buckets[model]["sonnet_pass_ceis_fail"], prefer_classA=True)
        if cand:
            chosen["2_sonnet_pass_ceis_fail"] = cand
            break

    # Bucket 3: sonnet-fail + CEIS-pass (prefer Opus)
    for model in [OPUS, GPT]:
        cand = pick_best(all_buckets[model]["sonnet_fail_ceis_pass"])
        if cand:
            chosen["3_sonnet_fail_ceis_pass"] = cand
            break

    # Bucket 4: study3 fail (prefer Opus)
    for model in [OPUS, GPT]:
        s3 = scan_study3(model)
        s3_fails = [e for e in s3 if not e["ceis_pass"]]
        s3_passes = [e for e in s3 if e["ceis_pass"]]
        print(f"\n  Study 3 [{model}]: {len(s3)} trajectories (PASS: {len(s3_passes)}, FAIL: {len(s3_fails)})")
        if s3_fails:
            s3_fails.sort(key=lambda x: x["classA"], reverse=True)
            chosen["4_study3_fail"] = s3_fails[0]
            break

    # Print detailed entries
    labels = {
        "1_agree_pass": "1. AGREE-PASS (Sonnet PASS + CEIS PASS)",
        "2_sonnet_pass_ceis_fail": "2. SONNET-PASS + CEIS-FAIL (grader disagreement)",
        "3_sonnet_fail_ceis_pass": "3. SONNET-FAIL + CEIS-PASS (reversed disagreement)",
        "4_study3_fail": "4. STUDY 3 FAIL (100% fail)",
    }
    for key, label in labels.items():
        if key in chosen:
            print_entry(label, chosen[key])
        else:
            print(f"\n  [!] No trajectory found for: {label}")

    # Summary
    print(f"\n{'='*70}")
    print("  SUMMARY: 4 Forensic Trajectory IDs")
    print(f"{'='*70}")
    for key in ["1_agree_pass", "2_sonnet_pass_ceis_fail", "3_sonnet_fail_ceis_pass", "4_study3_fail"]:
        if key in chosen:
            e = chosen[key]
            short_label = labels[key].split("(")[0].strip()
            model_short = "Opus 4.5" if "opus" in e["model"] else "GPT-5.2"
            print(f"  {short_label:45s}  {e['scenario_id']:20s}  ({e['condition']}, {model_short})")

    # Note on bucket 2
    opus_b2 = len(all_buckets[OPUS]["sonnet_pass_ceis_fail"])
    if opus_b2 == 0 and "2_sonnet_pass_ceis_fail" in chosen:
        print(f"\n  NOTE: Bucket 2 has 0 entries for Opus 4.5 (Sonnet never passed")
        print(f"        where CEIS failed). Using GPT-5.2 trajectory instead.")
        print(f"        This means for Opus: whenever Sonnet said PASS, CEIS agreed.")
        print(f"        All 360 disagreements are Sonnet-FAIL/CEIS-PASS (bucket 3).")


if __name__ == "__main__":
    main()
