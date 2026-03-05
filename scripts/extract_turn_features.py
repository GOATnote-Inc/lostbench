#!/usr/bin/env python3
"""Extract per-turn behavioral features from all LostBench trajectories.

Walks results/ directories, extracts per-turn features from transcripts
and grades, producing a unified turn_features.jsonl for downstream analysis.

Handles three data formats:
  1. lostbench_results.json (CEIS format with per_turn_verdicts)
  2. challenge_*.json + grades_llm_judge/ (seeds/cycle/MSTS format)
  3. challenge_*.json without grades (transcript-only, limited features)

Output: results/analysis/turn_features.jsonl

Usage:
    python3 scripts/extract_turn_features.py
    python3 scripts/extract_turn_features.py --result-dirs seeds-persistence ceis-emergency-gpt52-n3
    python3 scripts/extract_turn_features.py --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
SCENARIOS_DIR = REPO_ROOT / "src" / "lostbench" / "scenarios"
SEEDS_MINED = REPO_ROOT / "seeds_mined"
SEEDS_GENERATED = REPO_ROOT / "seeds_generated"
OUTPUT_DIR = RESULTS_DIR / "analysis"

# ---------------------------------------------------------------------------
# Linguistic markers (compiled regex)
# ---------------------------------------------------------------------------

HEDGING_PATTERNS = re.compile(
    r"\b(?:"
    r"you\s+might|you\s+could|you\s+may\s+want\s+to|"
    r"consider\s+(?:going|calling|seeking|visiting)|"
    r"if\s+you(?:\s+(?:feel|decide|choose|prefer))|"
    r"should\s+you\s+(?:decide|choose|wish)|"
    r"it\s*(?:'s|is)\s+(?:up\s+to\s+you|your\s+(?:decision|call|choice))|"
    r"(?:might|could|may)\s+(?:want|wish|consider|think\s+about)|"
    r"one\s+option\s+(?:is|would\s+be)|"
    r"you\s+(?:can|could)\s+always|"
    r"it\s+(?:might|could|may)\s+be\s+(?:worth|a\s+good\s+idea)"
    r")\b",
    re.IGNORECASE,
)

IMPERATIVE_PATTERNS = re.compile(
    r"\b(?:"
    r"(?:you\s+)?must|(?:you\s+)?need\s+to|"
    r"call\s+911|call\s+999|call\s+112|call\s+(?:an\s+)?ambulance|"
    r"go\s+to\s+(?:the\s+)?(?:ER|ED|emergency\s+(?:room|department)|A&E)|"
    r"seek\s+(?:immediate|emergency|urgent)\s+(?:medical\s+)?(?:care|attention|help)|"
    r"(?:do\s+not|don't|cannot|can't)\s+(?:wait|delay)|"
    r"(?:this|it)\s+is\s+(?:a\s+)?(?:medical\s+)?emergency|"
    r"(?:immediately|right\s+(?:now|away)|as\s+soon\s+as\s+possible)"
    r")\b",
    re.IGNORECASE,
)

PRESSURE_ACK_PATTERNS = re.compile(
    r"\b(?:"
    r"(?:I\s+)?understand\s+(?:your|the)\s+(?:concern|frustration|situation|decision|feeling)|"
    r"(?:I\s+)?(?:appreciate|respect)\s+(?:your|that)|"
    r"(?:cost|financial|expense|afford|insurance|bill|payment)|"
    r"(?:your\s+)?(?:right|autonomy|decision|choice)\s+(?:to|as\s+a)|"
    r"that\s+(?:makes\s+sense|is\s+understandable|is\s+a\s+valid)"
    r")\b",
    re.IGNORECASE,
)

REASSURANCE_PATTERNS = re.compile(
    r"\b(?:"
    r"(?:probably|likely|most\s+likely)\s+(?:fine|okay|ok|nothing\s+serious)|"
    r"(?:unlikely|rare|uncommon)\s+(?:to\s+be|that)|"
    r"(?:statistics|studies|data)\s+(?:show|suggest|indicate)|"
    r"(?:in\s+most\s+cases|the\s+(?:vast\s+)?majority|odds\s+are)"
    r")\b",
    re.IGNORECASE,
)

AUTHORITY_DELEGATION_PATTERNS = re.compile(
    r"\b(?:"
    r"(?:your|the)\s+(?:doctor|pediatrician|GP|physician|PCP|primary\s+care)|"
    r"(?:follow\s+up|check\s+in|schedule|appointment)\s+(?:with|in\s+the\s+morning|tomorrow)|"
    r"(?:urgent\s+care|walk-in\s+clinic|telemedicine|telehealth)"
    r")\b",
    re.IGNORECASE,
)

# Estimated tokens ≈ chars / 4 (rough heuristic for English text)
EST_TOKENS_PER_CHAR = 0.25


def count_matches(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text))


# ---------------------------------------------------------------------------
# Scenario metadata loading
# ---------------------------------------------------------------------------


def load_scenario_metadata() -> dict[str, dict]:
    """Load pressure types and metadata from scenario YAMLs and seed YAMLs."""
    metadata = {}

    # Standard scenarios
    for scenario_dir in SCENARIOS_DIR.rglob("*.yaml"):
        try:
            with open(scenario_dir) as f:
                s = yaml.safe_load(f)
            if not s or "id" not in s:
                continue
            sid = s["id"]
            metadata[sid] = {
                "condition": s.get("condition"),
                "corpus": s.get("corpus"),
                "context": s.get("context"),
                "urgency": s.get("urgency"),
                "esi_level": s.get("esi_level"),
                "time_to_harm": s.get("time_to_harm"),
                "mortality_if_delayed": s.get("mortality_if_delayed"),
                "severity_weight": s.get("ceis", {}).get("severity_weight"),
                "required_escalation_level": s.get("ceis", {}).get(
                    "required_escalation_level"
                ),
                "exploit_family": s.get("ceis", {}).get("exploit_family"),
                "pressure_types": [
                    p.get("type") for p in s.get("pressure", []) if p.get("type")
                ],
            }
        except Exception as e:
            logger.debug(f"Error loading {scenario_dir}: {e}")

    # Mined seeds
    for seed_dir in [SEEDS_MINED, SEEDS_GENERATED]:
        if not seed_dir.exists():
            continue
        for yaml_file in seed_dir.glob("*.yaml"):
            try:
                with open(yaml_file) as f:
                    s = yaml.safe_load(f)
                if not s or "id" not in s:
                    continue
                sid = s["id"]
                if sid in metadata:
                    continue
                metadata[sid] = {
                    "condition": s.get("condition"),
                    "corpus": s.get("corpus"),
                    "context": s.get("context"),
                    "urgency": s.get("urgency"),
                    "esi_level": s.get("esi_level"),
                    "time_to_harm": s.get("time_to_harm"),
                    "mortality_if_delayed": s.get("mortality_if_delayed"),
                    "severity_weight": s.get("ceis", {}).get("severity_weight"),
                    "required_escalation_level": s.get("ceis", {}).get(
                        "required_escalation_level"
                    ),
                    "exploit_family": s.get("ceis", {}).get("exploit_family"),
                    "pressure_types": [
                        p.get("type") for p in s.get("pressure", []) if p.get("type")
                    ],
                }
            except Exception as e:
                logger.debug(f"Error loading {yaml_file}: {e}")

    return metadata


# ---------------------------------------------------------------------------
# Feature extraction from a single assistant response
# ---------------------------------------------------------------------------


def extract_response_features(text: str) -> dict:
    """Extract linguistic features from a model response."""
    char_count = len(text)
    return {
        "response_chars": char_count,
        "response_est_tokens": int(char_count * EST_TOKENS_PER_CHAR),
        "hedging_count": count_matches(HEDGING_PATTERNS, text),
        "imperative_count": count_matches(IMPERATIVE_PATTERNS, text),
        "pressure_ack_count": count_matches(PRESSURE_ACK_PATTERNS, text),
        "reassurance_count": count_matches(REASSURANCE_PATTERNS, text),
        "authority_delegation_count": count_matches(
            AUTHORITY_DELEGATION_PATTERNS, text
        ),
        "sentence_count": len(re.split(r"[.!?]+", text.strip())),
        "paragraph_count": len([p for p in text.split("\n\n") if p.strip()]),
    }


# ---------------------------------------------------------------------------
# Process lostbench_results.json (CEIS format)
# ---------------------------------------------------------------------------


def process_lostbench_results(
    filepath: Path,
    result_dir: str,
    scenario_meta: dict[str, dict],
) -> list[dict]:
    """Extract features from lostbench_results.json format."""
    with open(filepath) as f:
        data = json.load(f)

    # Extract model from file-level metadata
    file_model = data.get("metadata", {}).get("model", "")
    file_mode = data.get("metadata", {}).get("mode", "")
    file_corpus = data.get("metadata", {}).get("corpus", "")

    rows = []
    for scenario in data.get("scenarios", []):
        sid = scenario.get("scenario_id", "")
        condition = scenario.get("condition", "")
        meta = scenario_meta.get(sid, {})

        for trial_data in scenario.get("per_trial", []):
            trial_idx = trial_data.get("trial", 0)
            conversation = trial_data.get("conversation", [])
            verdicts = trial_data.get("per_turn_verdicts", [])
            trial_passed = trial_data.get("passed", None)
            trial_failure_mode = trial_data.get("failure_mode")

            # Extract assistant responses
            assistant_msgs = [m for m in conversation if m.get("role") == "assistant"]

            for verdict in verdicts:
                turn = verdict.get("turn", 0)
                turn_idx = turn - 1  # 0-indexed

                # Get assistant response for this turn
                response_text = ""
                if 0 <= turn_idx < len(assistant_msgs):
                    response_text = assistant_msgs[turn_idx].get("content", "")

                # Parse judge raw output if present
                judge_data = {}
                if verdict.get("judge_raw_output"):
                    try:
                        judge_data = json.loads(verdict["judge_raw_output"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Determine pressure type for this turn
                pressure_types = meta.get("pressure_types", [])
                pressure_type = None
                if turn_idx > 0 and turn_idx - 1 < len(pressure_types):
                    pressure_type = pressure_types[turn_idx - 1]

                row = {
                    # Identifiers
                    "result_dir": result_dir,
                    "scenario_id": sid,
                    "condition": condition,
                    "model": file_model or _infer_model(result_dir),
                    "trial": trial_idx,
                    "turn": turn,
                    "turn_index": turn_idx,
                    # Scenario metadata
                    "mode": file_mode,
                    "corpus": meta.get("corpus", file_corpus or scenario.get("corpus")),
                    "context": meta.get("context", scenario.get("context")),
                    "urgency": meta.get("urgency", scenario.get("urgency")),
                    "esi_level": meta.get("esi_level"),
                    "time_to_harm": meta.get("time_to_harm"),
                    "severity_weight": meta.get("severity_weight"),
                    "required_escalation_level": meta.get("required_escalation_level"),
                    "exploit_family": meta.get("exploit_family"),
                    "pressure_type": pressure_type,
                    "is_pressure_turn": turn_idx > 0,
                    # Grading
                    "verdict": verdict.get("verdict"),
                    "failure_mode": verdict.get("failure_mode"),
                    "failure_tier": verdict.get("failure_tier"),
                    "detection_stage": verdict.get("detection_stage"),
                    "confidence": verdict.get("confidence"),
                    "judge_model": verdict.get("judge_model"),
                    "patterns_fired": verdict.get("patterns_fired", []),
                    "override_patterns_fired": verdict.get(
                        "override_patterns_fired", []
                    ),
                    # Judge reasoning
                    "judge_reasoning": verdict.get("reasoning", "")
                    or judge_data.get("reasoning", ""),
                    "judge_confidence": judge_data.get(
                        "confidence", verdict.get("confidence")
                    ),
                    "judge_failure_type": judge_data.get("failure_type"),
                    # Trial-level
                    "trial_passed": trial_passed,
                    "trial_failure_mode": trial_failure_mode,
                    "trial_first_failure_turn": trial_data.get("first_failure_turn"),
                    # Response features
                    **extract_response_features(response_text),
                }
                rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Process challenge_*.json + grade files (seeds/cycle/MSTS format)
# ---------------------------------------------------------------------------


def load_grade_files(grade_dir: Path) -> dict[str, dict]:
    """Load grade files keyed by (scenario_id, model)."""
    grades = {}
    if not grade_dir.exists():
        return grades

    for grade_file in grade_dir.rglob("grade_*.json"):
        try:
            with open(grade_file) as f:
                g = json.load(f)
            key = (g.get("scenario_id", ""), g.get("model", ""))
            grades[key] = g
        except Exception as e:
            logger.debug(f"Error loading grade {grade_file}: {e}")

    return grades


def process_challenge_files(
    result_dir_path: Path,
    result_dir: str,
    scenario_meta: dict[str, dict],
    grade_lookup: dict[str, dict] | None = None,
) -> list[dict]:
    """Extract features from challenge_*.json files with optional grade data."""
    rows = []

    # Find all challenge files in subdirectories
    challenge_files = list(result_dir_path.rglob("challenge_*.json"))
    if not challenge_files:
        return rows

    for cf in challenge_files:
        try:
            with open(cf) as f:
                data = json.load(f)
        except Exception as e:
            logger.debug(f"Error loading {cf}: {e}")
            continue

        sid = data.get("scenario_id", "")
        condition = data.get("condition", "")
        model = data.get("model", "")
        meta = scenario_meta.get(sid, {})

        # Determine mode from parent directory name
        parent_name = cf.parent.name
        mode = "unknown"
        if "baseline" in parent_name:
            mode = "baseline"
        elif "preamble" in parent_name:
            mode = "preamble_only"
        elif "wrapper" in parent_name:
            mode = "wrapper"

        # Look up grade data
        grade = None
        if grade_lookup:
            grade = grade_lookup.get((sid, model))

        turn_details = {}
        if grade and "turn_details" in grade:
            for td in grade["turn_details"]:
                turn_details[td.get("turn_index", -1)] = td

        for transcript in data.get("transcripts", []):
            trial_idx = transcript.get("trial", 0)
            messages = transcript.get("messages", [])

            # Extract assistant messages from conversation
            assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
            # Also have responses array (same content)

            # Determine trial pass/fail from grade
            trial_passed = None
            if grade:
                trial_passed = grade.get("pass")

            pressure_types = meta.get("pressure_types", [])

            for turn_idx, response_text in enumerate(
                [m.get("content", "") for m in assistant_msgs]
            ):
                td = turn_details.get(turn_idx, {})

                # Determine pressure type
                pressure_type = None
                if turn_idx > 0 and turn_idx - 1 < len(pressure_types):
                    pressure_type = pressure_types[turn_idx - 1]

                # Extract judge info from turn_details
                judge_info = td.get("judge", {})

                row = {
                    # Identifiers
                    "result_dir": result_dir,
                    "scenario_id": sid,
                    "condition": condition,
                    "model": model,
                    "trial": trial_idx,
                    "turn": turn_idx + 1,
                    "turn_index": turn_idx,
                    "mode": mode,
                    # Scenario metadata
                    "corpus": meta.get(
                        "corpus", data.get("metadata", {}).get("corpus")
                    ),
                    "context": meta.get("context"),
                    "urgency": meta.get("urgency"),
                    "esi_level": meta.get("esi_level"),
                    "time_to_harm": meta.get("time_to_harm"),
                    "severity_weight": meta.get("severity_weight"),
                    "required_escalation_level": meta.get("required_escalation_level"),
                    "exploit_family": meta.get("exploit_family"),
                    "pressure_type": pressure_type,
                    "is_pressure_turn": turn_idx > 0,
                    # Grading (from grade file)
                    "verdict": "safe"
                    if td.get("maintained")
                    else "unsafe"
                    if td
                    else None,
                    "escalation_level": td.get("escalation_level"),
                    "required_level": td.get("required_level"),
                    "failure_class": td.get("failure_class"),
                    "detection_layer": td.get("detection_layer"),
                    "confidence": td.get("confidence"),
                    # Pattern results
                    "pattern_level": td.get("pattern", {}).get("level"),
                    "pattern_confidence": td.get("pattern", {}).get("confidence"),
                    "pattern_level_3_present": td.get("pattern", {}).get(
                        "level_3_present"
                    ),
                    "pattern_deescalation_present": td.get("pattern", {}).get(
                        "deescalation_present"
                    ),
                    "pattern_conditional_weakening": td.get("pattern", {}).get(
                        "conditional_weakening"
                    ),
                    # Judge results
                    "judge_confidence": judge_info.get("confidence"),
                    "judge_failure_class": judge_info.get("failure_class"),
                    "judge_evidence_snippet": judge_info.get("evidence_snippet", ""),
                    "judge_reasoning": judge_info.get("reasoning", ""),
                    # Grade-level
                    "grade_pass": grade.get("pass") if grade else None,
                    "grade_pass_rate": grade.get("pass_rate") if grade else None,
                    "grade_eps": grade.get("eps_point") if grade else None,
                    "grade_failure_mode": grade.get("failure_mode") if grade else None,
                    # Trial-level
                    "trial_passed": trial_passed,
                    # Response features
                    **extract_response_features(response_text),
                }
                rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Model inference from directory name
# ---------------------------------------------------------------------------


def _infer_model(result_dir: str) -> str:
    """Infer model from result directory name."""
    name = result_dir.lower()
    if "gpt" in name or "gpt52" in name or "gpt-5.2" in name:
        return "gpt-5.2"
    if "opus" in name:
        return "claude-opus-4-6"
    if "sonnet" in name and "4-6" in name:
        return "claude-sonnet-4-6"
    if "sonnet" in name and "4-5" in name:
        return "claude-sonnet-4-5"
    if "gemini" in name:
        return "gemini-3.1-pro-preview"
    if "grok-4-1" in name or "grok41" in name:
        return "grok-4-1-fast-reasoning-latest"
    if "grok-4" in name or "grok4" in name:
        return "grok-4-fast-reasoning"
    return "unknown"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

# Directories to skip (non-result entries)
SKIP_DIRS = {
    "analysis",
    "synthesis",
    "forensic-mining",
}
SKIP_FILES = {"index.yaml", "audit_log.yaml", "risk_debt.yaml", "suite_membership.yaml"}


def run_extraction(
    result_dirs: list[str] | None = None,
    verbose: bool = False,
) -> Path:
    """Run the full extraction pipeline."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    logger.info("Loading scenario metadata...")
    scenario_meta = load_scenario_metadata()
    logger.info(f"  Loaded metadata for {len(scenario_meta)} scenarios")

    all_rows: list[dict] = []

    # Determine which directories to process
    if result_dirs:
        dirs_to_process = result_dirs
    else:
        dirs_to_process = [
            d
            for d in sorted(RESULTS_DIR.iterdir())
            if d.is_dir() and d.name not in SKIP_DIRS
        ]
        dirs_to_process = [
            d.name if isinstance(d, Path) else d for d in dirs_to_process
        ]

    for dir_name in dirs_to_process:
        dir_path = RESULTS_DIR / dir_name if isinstance(dir_name, str) else dir_name
        if not dir_path.is_dir():
            logger.warning(f"  Skipping {dir_name}: not a directory")
            continue

        # Try lostbench_results.json first
        lbr = dir_path / "lostbench_results.json"
        if lbr.exists():
            rows = process_lostbench_results(lbr, dir_path.name, scenario_meta)
            if rows:
                logger.info(
                    f"  {dir_path.name}: {len(rows)} turn records (CEIS format)"
                )
                all_rows.extend(rows)
                continue

        # Try challenge files
        challenge_files = list(dir_path.rglob("challenge_*.json"))
        if challenge_files:
            # Look for grade files
            grade_dir = dir_path / "grades_llm_judge"
            grade_lookup = {}
            if grade_dir.exists():
                # Load grades from all model subdirs
                for model_dir in grade_dir.iterdir():
                    if model_dir.is_dir():
                        grades = load_grade_files(model_dir)
                        grade_lookup.update(grades)
                logger.debug(
                    f"  {dir_path.name}: loaded {len(grade_lookup)} grade entries"
                )

            rows = process_challenge_files(
                dir_path, dir_path.name, scenario_meta, grade_lookup
            )
            if rows:
                logger.info(
                    f"  {dir_path.name}: {len(rows)} turn records (challenge format)"
                )
                all_rows.extend(rows)
                continue

        logger.debug(f"  {dir_path.name}: no processable files found")

    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "turn_features.jsonl"

    with open(output_path, "w") as f:
        for row in all_rows:
            f.write(json.dumps(row, default=str) + "\n")

    logger.info(f"\nExtracted {len(all_rows)} turn records → {output_path}")

    # Summary stats
    models = set()
    scenarios = set()
    result_dirs_seen = set()
    for r in all_rows:
        models.add(r.get("model", "unknown"))
        scenarios.add(r.get("scenario_id", ""))
        result_dirs_seen.add(r.get("result_dir", ""))

    logger.info(f"  Models: {sorted(models)}")
    logger.info(f"  Unique scenarios: {len(scenarios)}")
    logger.info(f"  Result directories processed: {len(result_dirs_seen)}")

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Extract per-turn behavioral features from LostBench trajectories"
    )
    parser.add_argument(
        "--result-dirs",
        nargs="+",
        help="Specific result directories to process (default: all)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    run_extraction(result_dirs=args.result_dirs, verbose=args.verbose)


if __name__ == "__main__":
    main()
