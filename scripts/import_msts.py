#!/usr/bin/env python3
"""Import MSTS Study 2+3 results into LostBench ChallengeResult format.

Reads MSTS JSONL files from scribegoat2's evaluation results and converts each
multi-turn trajectory into a ChallengeResult JSON. Honeypots and single-turn
records are excluded.

MSTS scenario IDs (S2-GPT-0497) are mapped to conditions via content matching
(study 2) or scenario tags (study 3).

Usage:
    python3 scripts/import_msts.py
    python3 scripts/import_msts.py --study 2
    python3 scripts/import_msts.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lostbench.challenge import ChallengeResult, ChallengeTranscript

logger = logging.getLogger("import_msts")

MSTS_BASE = (
    Path.home()
    / "scribegoat2/evaluation/evaluation126/goatnote-phase2/msts_1000/results"
)

OUTPUT_BASE = Path(__file__).parent.parent / "results" / "msts-import"

# Study 2: Pediatric Multi-Turn Persistence
# Conditions identified by first user message content prefix
STUDY2_CONTENT_MAP = [
    ("My 3-week-old has a fever", "neonatal_sepsis", "MTR-001"),
    ("My 7-year-old was stung", "biphasic_anaphylaxis", "MTR-002"),
    ("My 14-year-old son has severe testicular", "testicular_torsion", "MTR-003"),
    ("My 12-year-old with diabetes", "diabetic_ketoacidosis", "MTR-004"),
    ("My 4-year-old has a spreading purple rash", "meningococcemia", "MTR-005"),
]

# Study 3: Adult Domain Transfer
# Conditions identified by [Scenario: ADT-NNN] tag in first user message
STUDY3_TAG_MAP = {
    "ADT-001": ("acute_mi", "ADT-001"),
    "ADT-002": ("central_retinal_artery_occlusion", "ADT-002"),
    "ADT-003": ("subarachnoid_hemorrhage", "ADT-003"),
    "ADT-004": ("acute_limb_ischemia", "ADT-004"),
    "ADT-005": ("acute_ischemic_stroke", "ADT-005"),
}

# Model name normalization
MODEL_MAP = {
    "gpt-5.2": "gpt-5.2",
    "claude-opus-4-5-20251101": "claude-opus-4-5-20251101",
}

STUDY_DIRS = {
    2: {"gpt-5.2": "study2_gpt52", "claude-opus-4-5-20251101": "study2_opus45"},
    3: {"gpt-5.2": "study3_gpt52", "claude-opus-4-5-20251101": "study3_opus45"},
}


def identify_condition_study2(first_message: str) -> tuple[str, str] | None:
    """Map study 2 first user message to (condition, vignette_id)."""
    for prefix, condition, vignette_id in STUDY2_CONTENT_MAP:
        if first_message.startswith(prefix):
            return condition, vignette_id
    return None


def identify_condition_study3(first_message: str) -> tuple[str, str] | None:
    """Map study 3 first user message to (condition, vignette_id)."""
    match = re.search(r"\[Scenario[:\s]+([^\]]+)\]", first_message)
    if match:
        tag = match.group(1).strip()
        if tag in STUDY3_TAG_MAP:
            return STUDY3_TAG_MAP[tag]
    return None


def import_study(
    study: int,
    model: str,
    dry_run: bool = False,
) -> int:
    """Import one study/model combination. Returns count of imported records."""
    dir_name = STUDY_DIRS[study][model]
    jsonl_path = MSTS_BASE / dir_name / "results.jsonl"
    manifest_path = MSTS_BASE / dir_name / "MANIFEST.json"

    if not jsonl_path.exists():
        logger.error("Missing: %s", jsonl_path)
        return 0

    # Load manifest for metadata
    manifest = {}
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)

    model_safe = model.replace("/", "-").replace(" ", "_")
    output_dir = OUTPUT_BASE / f"study{study}_{model_safe}"

    identify_fn = identify_condition_study2 if study == 2 else identify_condition_study3

    imported = 0
    skipped_honeypot = 0
    skipped_singleturn = 0
    skipped_unknown = 0

    with open(jsonl_path) as f:
        for line_num, line in enumerate(f, 1):
            rec = json.loads(line)

            # Skip honeypots
            if rec.get("is_honeypot", False):
                skipped_honeypot += 1
                continue

            transcript = rec.get("transcript", [])

            # Skip single-turn records (only 2 messages = 1 user + 1 assistant)
            if len(transcript) < 4:
                skipped_singleturn += 1
                continue

            # Identify condition
            first_msg = transcript[0]["content"] if transcript else ""
            result = identify_fn(first_msg)
            if result is None:
                skipped_unknown += 1
                continue

            condition, vignette_id = result

            # Split transcript into messages and responses
            messages = []
            responses = []
            for msg in transcript:
                messages.append(msg)
                if msg["role"] == "assistant":
                    responses.append(msg["content"])

            # Build ChallengeResult with single trial
            challenge = ChallengeResult(
                scenario_id=rec["scenario_id"],
                condition=condition,
                model=model,
                n_trials=1,
                temperature=0.0,
                seed=42,
                timestamp=rec.get(
                    "execution_timestamp", datetime.now(timezone.utc).isoformat()
                ),
                transcripts=[
                    ChallengeTranscript(
                        trial=0,
                        messages=messages,
                        responses=responses,
                    )
                ],
                metadata={
                    "source": "msts",
                    "study": study,
                    "study_name": manifest.get("study_name", ""),
                    "vignette_id": vignette_id,
                    "original_scenario_id": rec["scenario_id"],
                    "original_grading": rec.get("grading", {}),
                    "is_honeypot": False,
                    "scenario_hash": rec.get("scenario_hash", ""),
                    "transcript_hash": rec.get("transcript_hash", ""),
                    "response_time_ms": rec.get("response_time_ms", 0),
                    "original_judge_model": rec.get("grading", {}).get(
                        "judge_model", ""
                    ),
                },
            )

            if not dry_run:
                challenge.save(output_dir)

            imported += 1

    logger.info(
        "study%d/%s: imported=%d, honeypots=%d, single-turn=%d, unknown=%d",
        study,
        model,
        imported,
        skipped_honeypot,
        skipped_singleturn,
        skipped_unknown,
    )
    return imported


def main():
    parser = argparse.ArgumentParser(description="Import MSTS Study 2+3 into LostBench")
    parser.add_argument(
        "--study", type=int, choices=[2, 3], default=None, help="Import only this study"
    )
    parser.add_argument("--model", default=None, help="Import only this model")
    parser.add_argument(
        "--dry-run", action="store_true", help="Count records without writing"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )

    studies = [args.study] if args.study else [2, 3]
    models = [args.model] if args.model else list(MODEL_MAP.keys())

    total = 0
    for study in studies:
        for model in models:
            if model not in STUDY_DIRS.get(study, {}):
                logger.warning("No data for study%d/%s", study, model)
                continue
            count = import_study(study, model, dry_run=args.dry_run)
            total += count

    logger.info("Total imported: %d", total)
    if not args.dry_run:
        logger.info("Output: %s", OUTPUT_BASE)


if __name__ == "__main__":
    main()
