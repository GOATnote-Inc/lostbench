#!/usr/bin/env python3
"""
LostBench — Cross-Judge Calibration Diff Analysis

Deterministic, no-API diagnostic explaining where and why judges disagree.
Derived solely from stored artifacts.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Expected judge keys (sorted for determinism)
EXPECTED_JUDGES = ("claude", "gemini", "gpt")

# Classification taxonomy — keyed by (claude_safe, gpt_safe, gemini_safe)
CLASSIFICATION_TABLE = {
    (True, True, True): "UNANIMOUS_SAFE",
    (False, False, False): "UNANIMOUS_UNSAFE",
    (True, False, True): "GPT_STRICTER",
    (True, True, False): "GEMINI_STRICTER",
    (False, True, True): "CLAUDE_STRICTER",
    (False, False, True): "CLAUDE_GPT_STRICT",
    (False, True, False): "CLAUDE_GEMINI_STRICT",
    (True, False, False): "GPT_GEMINI_STRICT",
}

# Report ordering for disagreement types
DISAGREEMENT_ORDER = [
    "GPT_STRICTER",
    "CLAUDE_STRICTER",
    "GEMINI_STRICTER",
    "CLAUDE_GPT_STRICT",
    "CLAUDE_GEMINI_STRICT",
    "GPT_GEMINI_STRICT",
]


def sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fail(msg: str):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg: str):
    print(f"  {msg}", file=sys.stderr)


def warn(msg: str):
    print(f"  WARN: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# A) Schema validation
# ---------------------------------------------------------------------------


def validate_schema(data: dict):
    if "cross_model" not in data:
        fail("Missing 'cross_model' in validation file")

    cm = data["cross_model"]

    if "details" not in cm:
        fail("Missing 'cross_model.details'")

    details = cm["details"]
    if not details:
        fail("'cross_model.details' is empty")

    if "sample_size" in cm and cm["sample_size"] != len(details):
        fail(f"sample_size ({cm['sample_size']}) != len(details) ({len(details)})")

    expected_set = set(EXPECTED_JUDGES)

    for i, sample in enumerate(details):
        for field in ("scenario_id", "trial", "model"):
            if field not in sample:
                fail(f"details[{i}] missing required field '{field}'")

        if "verdicts" not in sample:
            fail(f"details[{i}] missing 'verdicts'")

        judge_keys = set(sample["verdicts"].keys())
        if judge_keys != expected_set:
            fail(
                f"details[{i}] unexpected judge keys: {judge_keys} "
                f"(expected {expected_set})"
            )

        for judge in EXPECTED_JUDGES:
            v = sample["verdicts"][judge]
            if "semantic_safe" not in v:
                fail(f"details[{i}].verdicts.{judge} missing 'semantic_safe'")
            if not isinstance(v["semantic_safe"], bool):
                fail(f"details[{i}].verdicts.{judge}.semantic_safe not boolean")
            if "confidence" in v and v["confidence"] is not None:
                if not isinstance(v["confidence"], (int, float)):
                    fail(f"details[{i}].verdicts.{judge}.confidence not numeric")
                if not (0.0 <= v["confidence"] <= 1.0):
                    fail(
                        f"details[{i}].verdicts.{judge}.confidence="
                        f"{v['confidence']} out of [0,1]"
                    )
            if "error" in v and not isinstance(v["error"], bool):
                fail(f"details[{i}].verdicts.{judge}.error not boolean")

    info("Schema validation passed")


# ---------------------------------------------------------------------------
# B) Agreement recomputation (tamper detection)
# ---------------------------------------------------------------------------


def recompute_agreement(data: dict) -> tuple[dict, float]:
    cm = data["cross_model"]
    details = cm["details"]

    pairs = [("claude", "gpt"), ("claude", "gemini"), ("gpt", "gemini")]
    agree_count = {p: 0 for p in pairs}
    valid_count = {p: 0 for p in pairs}

    for sample in details:
        verdicts = sample["verdicts"]
        for a, b in pairs:
            if verdicts[a].get("error", False) or verdicts[b].get("error", False):
                continue
            valid_count[(a, b)] += 1
            if verdicts[a]["semantic_safe"] == verdicts[b]["semantic_safe"]:
                agree_count[(a, b)] += 1

    pairwise = {}
    for pair in pairs:
        key = f"{pair[0]}_vs_{pair[1]}"
        if valid_count[pair] > 0:
            pairwise[key] = agree_count[pair] / valid_count[pair]
        else:
            pairwise[key] = None

    valid_rates = [v for v in pairwise.values() if v is not None]
    recomputed_mean = sum(valid_rates) / len(valid_rates) if valid_rates else 0.0

    stored_mean = cm.get("judge_cross_model_agreement", 0.0)
    diff = abs(recomputed_mean - stored_mean)

    info(f"Recomputed agreement: {recomputed_mean:.4f}")
    info(f"Stored agreement:     {stored_mean:.4f}")
    info(f"Difference:           {diff:.6f}")

    if diff > 0.01:
        fail(
            f"Agreement recomputation mismatch: recomputed={recomputed_mean:.4f}, "
            f"stored={stored_mean:.4f}, diff={diff:.4f} > 0.01"
        )

    info("Tamper detection passed")
    return pairwise, recomputed_mean


# ---------------------------------------------------------------------------
# C) Model → directory mapping
# ---------------------------------------------------------------------------


def build_model_directory_map(results_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for d in sorted(results_dir.iterdir()):
        if not d.is_dir():
            continue
        results_file = d / "emergency" / "lostbench_results.json"
        if not results_file.exists():
            continue
        model_id = d.name
        if model_id in mapping:
            fail(f"Duplicate model directory for '{model_id}'")
        mapping[model_id] = d.name

    info("Model -> directory mapping:")
    for model_id in sorted(mapping):
        info(f"  {model_id} -> {mapping[model_id]}/")

    return mapping


def validate_model_mapping(details: list[dict], model_dir_map: dict[str, str]):
    """Ensure every model referenced in details exists in the mapping."""
    referenced_models = sorted(set(s["model"] for s in details))
    for model in referenced_models:
        if model not in model_dir_map:
            fail(
                f"Model '{model}' in details not found in directory mapping. "
                f"Available: {sorted(model_dir_map.keys())}"
            )


# ---------------------------------------------------------------------------
# Transcript index
# ---------------------------------------------------------------------------


def build_transcript_index(
    results_dir: Path, model_dir_map: dict[str, str]
) -> dict[tuple, list[dict]]:
    """Build (model, scenario_id, trial) -> conversation mapping."""
    index: dict[tuple, list[dict]] = {}

    for model_id, dir_name in sorted(model_dir_map.items()):
        results_file = results_dir / dir_name / "emergency" / "lostbench_results.json"
        with open(results_file) as f:
            data = json.load(f)

        for scenario in data.get("scenarios", []):
            sid = scenario.get("scenario_id")
            for trial_data in scenario.get("per_trial", []):
                trial_num = trial_data.get("trial")
                conversation = trial_data.get("conversation", [])
                key = (model_id, sid, trial_num)
                if key in index:
                    fail(f"Ambiguous trial mapping — duplicate key: {key}")
                index[key] = conversation

    info(f"Transcript index: {len(index)} entries")
    return index


def format_transcript(conversation: list[dict]) -> str:
    lines = []
    turn_num = 0
    for msg in conversation:
        role = msg.get("role", "unknown")
        content = msg.get("content", "").strip()
        if role == "user":
            turn_num += 1
            lines.append(f"Turn {turn_num} — User:\n{content}\n")
        elif role == "assistant":
            lines.append(f"Turn {turn_num} — Assistant:\n{content}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# D) Classification
# ---------------------------------------------------------------------------


def classify_verdicts(verdicts: dict) -> str:
    c = verdicts["claude"]["semantic_safe"]
    g = verdicts["gpt"]["semantic_safe"]
    m = verdicts["gemini"]["semantic_safe"]

    key = (c, g, m)
    classification = CLASSIFICATION_TABLE.get(key)
    if classification is None:
        fail(f"No classification for verdict tuple: claude={c}, gpt={g}, gemini={m}")
    return classification


# ---------------------------------------------------------------------------
# E) Majority for asymmetry
# ---------------------------------------------------------------------------


def majority_safe(verdicts: dict) -> bool:
    return sum(1 for v in verdicts.values() if v["semantic_safe"]) >= 2


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Cross-judge calibration diff analysis (deterministic, no-API)"
    )
    parser.add_argument("--validation-file", default="judge_validation.json")
    parser.add_argument("--results-dir", default="results/")
    parser.add_argument("--output", default="judge_disagreement_report.md")
    args = parser.parse_args()

    validation_path = Path(args.validation_file)
    results_dir = Path(args.results_dir)
    output_path = Path(args.output)

    # --- Load ---
    if not validation_path.exists():
        fail(f"Validation file not found: {validation_path}")
    with open(validation_path) as f:
        data = json.load(f)

    # --- A: Schema validation ---
    info("Validating schema...")
    validate_schema(data)

    # --- B: Tamper detection ---
    info("Recomputing agreement (tamper detection)...")
    pairwise_recomputed, mean_recomputed = recompute_agreement(data)

    # --- Model mapping ---
    info("Building model-directory mapping...")
    model_dir_map = build_model_directory_map(results_dir)

    details = data["cross_model"]["details"]
    validate_model_mapping(details, model_dir_map)

    # --- Transcript index ---
    info("Building transcript index...")
    transcript_index = build_transcript_index(results_dir, model_dir_map)

    # --- I: Deterministic ordering ---
    details_sorted = sorted(
        details,
        key=lambda s: (s["scenario_id"], s["trial"], s["model"]),
    )

    # --- C & D: Normalize verdicts and classify ---
    error_samples = []
    unanimous = []
    disagreements = []

    for sample in details_sorted:
        verdicts = sample["verdicts"]
        has_error = any(v.get("error", False) for v in verdicts.values())

        if has_error:
            error_samples.append(sample)
            continue

        classification = classify_verdicts(verdicts)
        sample["_classification"] = classification

        if classification.startswith("UNANIMOUS"):
            unanimous.append(sample)
        else:
            disagreements.append(sample)

    if not disagreements:
        fail("Zero disagreement cases found")

    # --- Classification counts ---
    classification_counts: dict[str, int] = {}
    for s in disagreements:
        c = s["_classification"]
        classification_counts[c] = classification_counts.get(c, 0) + 1

    # --- E: Calibration asymmetry ---
    asymmetry = {j: {"strict": 0, "lenient": 0} for j in EXPECTED_JUDGES}

    for sample in details_sorted:
        verdicts = sample["verdicts"]
        if any(v.get("error", False) for v in verdicts.values()):
            continue
        maj = majority_safe(verdicts)
        for judge in EXPECTED_JUDGES:
            j_safe = verdicts[judge]["semantic_safe"]
            if not j_safe and maj:
                asymmetry[judge]["strict"] += 1
            elif j_safe and not maj:
                asymmetry[judge]["lenient"] += 1

    # --- G: Check for violation_types ---
    has_violation_types = False
    for sample in details_sorted:
        for v in sample["verdicts"].values():
            if v.get("violation_types"):
                has_violation_types = True
                break

    # --- H: Confidence analysis ---
    safe_confs = []
    unsafe_confs = []
    for sample in disagreements:
        for v in sample["verdicts"].values():
            conf = v.get("confidence")
            if conf is not None:
                if v["semantic_safe"]:
                    safe_confs.append(conf)
                else:
                    unsafe_confs.append(conf)

    # --- F: Extract transcripts for disagreements ---
    cases = []
    for sample in disagreements:
        model = sample["model"]
        sid = sample["scenario_id"]
        trial = sample["trial"]

        key = (model, sid, trial)
        if key not in transcript_index:
            fail(f"Transcript not found for key={key}")

        conversation = transcript_index[key]
        formatted = format_transcript(conversation)

        user_turns = sum(1 for m in conversation if m.get("role") == "user")
        asst_turns = sum(1 for m in conversation if m.get("role") == "assistant")
        malformed = user_turns < 2 or asst_turns < 2
        if malformed:
            warn(f"Malformed transcript: {key} ({user_turns}u/{asst_turns}a)")

        transcript_hash = sha256_str(formatted)
        verdict_hashes = {}
        for judge in EXPECTED_JUDGES:
            blob = json.dumps(sample["verdicts"][judge], sort_keys=True)
            verdict_hashes[judge] = sha256_str(blob)

        judge_errors = sorted(
            j for j in EXPECTED_JUDGES if sample["verdicts"][j].get("error", False)
        )

        cases.append(
            {
                "sample": sample,
                "classification": sample["_classification"],
                "formatted_transcript": formatted,
                "transcript_hash": transcript_hash,
                "verdict_hashes": verdict_hashes,
                "judge_errors": judge_errors,
                "malformed": malformed,
            }
        )

    # ===================================================================
    # Build report
    # ===================================================================

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    header_lines = []
    summary_lines = []
    case_blocks = []  # list of list-of-lines, one per case

    # --- Header (file only) ---
    h = header_lines.append
    h("# Cross-Judge Calibration Diff Analysis")
    h("")
    h(f"**Generated:** {timestamp}")
    h(f"**Validation file:** `{validation_path}`")
    h(f"**Results directory:** `{results_dir}`")
    h("**Determinism:** No API calls. Derived solely from stored artifacts.")
    h("")
    h("### Model \u2192 Directory Mapping")
    h("")
    h("| Model ID | Directory |")
    h("|----------|-----------|")
    for mid in sorted(model_dir_map):
        h(f"| {mid} | `{model_dir_map[mid]}/` |")
    h("")

    # --- Summary (stdout + file) ---
    s = summary_lines.append
    s("---")
    s("")
    s("## Summary")
    s("")
    s(f"- **Total samples:** {len(details_sorted)}")
    s(f"- **Samples excluded (judge errors):** {len(error_samples)}")
    s(f"- **Unanimous agreement:** {len(unanimous)}")
    s(f"- **Disagreements:** {len(disagreements)}")
    s("")
    s("### Disagreement Breakdown")
    s("")
    for c in DISAGREEMENT_ORDER:
        s(f"- **{c}:** {classification_counts.get(c, 0)}")
    s("")
    s("### Calibration Asymmetry Index")
    s("")
    for judge in sorted(EXPECTED_JUDGES):
        a = asymmetry[judge]
        score = a["strict"] - a["lenient"]
        s(
            f"- **{judge.capitalize()}:** {score:+d} "
            f"(strict={a['strict']}, lenient={a['lenient']})"
        )
    s("")
    s("### Confidence Signals")
    s("")
    if safe_confs or unsafe_confs:
        if safe_confs:
            s(
                f"- **Mean SAFE confidence (disagreements):** "
                f"{sum(safe_confs) / len(safe_confs):.3f}"
            )
        else:
            s("- **Mean SAFE confidence:** insufficient data")
        if unsafe_confs:
            s(
                f"- **Mean UNSAFE confidence (disagreements):** "
                f"{sum(unsafe_confs) / len(unsafe_confs):.3f}"
            )
        else:
            s("- **Mean UNSAFE confidence:** insufficient data")
    else:
        s("- Confidence data not available; skipped.")
    s("")
    if not has_violation_types:
        s("> **Note:** Violation types not persisted; boolean verdicts only.")
        s("")

    # --- Per-case blocks ---
    for i, case in enumerate(cases, 1):
        block = []
        b = block.append
        sm = case["sample"]

        b("---")
        b("")
        b(f"## Case {i}: {sm['scenario_id']} / trial {sm['trial']} ({sm['model']})")
        b("")
        b(f"**Classification:** {case['classification']}")
        err_str = (
            "none" if not case["judge_errors"] else ", ".join(case["judge_errors"])
        )
        b(f"**Judge errors:** {err_str}")
        if case["malformed"]:
            b("**WARNING:** Transcript malformed (insufficient turns)")
        b(f"**Transcript SHA256:** `{case['transcript_hash']}`")
        b("")
        b("**Verdict hashes:**")
        for judge in EXPECTED_JUDGES:
            b(f"- {judge.capitalize()}: `{case['verdict_hashes'][judge]}`")
        b("")
        b("| Judge | Verdict | Confidence |")
        b("|-------|---------|------------|")
        for judge in ("claude", "gpt", "gemini"):
            v = sm["verdicts"][judge]
            verdict_str = "SAFE" if v["semantic_safe"] else "UNSAFE"
            conf = v.get("confidence")
            conf_str = f"{conf:.2f}" if conf is not None else "\u2014"
            b(f"| {judge.capitalize()} | {verdict_str} | {conf_str} |")
        b("")

        # Violation types
        b("**Violation types:**")
        any_vt = False
        for judge in ("claude", "gpt", "gemini"):
            vt = sm["verdicts"][judge].get("violation_types", [])
            if vt:
                any_vt = True
                normalized = sorted(set(t.strip().lower() for t in vt))
                b(f"- {judge.capitalize()}: {', '.join(normalized)}")
        if not any_vt:
            b("- \u2014")
        b("")

        b("### Transcript")
        b("")
        b("```")
        b(case["formatted_transcript"])
        b("```")
        b("")

        case_blocks.append(block)

    # ===================================================================
    # Write full report to file
    # ===================================================================

    all_lines = header_lines + summary_lines
    for block in case_blocks:
        all_lines.extend(block)

    with open(output_path, "w") as f:
        f.write("\n".join(all_lines))
    info(f"Report written to {output_path}")

    # ===================================================================
    # Stdout: summary + first case only
    # ===================================================================

    for line in summary_lines:
        print(line)
    if case_blocks:
        for line in case_blocks[0]:
            print(line)

    sys.exit(0)


if __name__ == "__main__":
    main()
