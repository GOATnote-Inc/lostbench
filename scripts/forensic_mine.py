#!/usr/bin/env python3
"""Forensic Mining: Cross-Repo Evaluation Data → Seed Hypotheses.

Bridges ScribeGoat2 (37K turn observations, 22 physician-adjudicated cases)
and LostBench (272 grade files, 2x2 + campaign results) into ranked mining
hypotheses for the failure-miner agent.

Follows the synthesize_risk.py pattern: load → build_* → render_*_md → write.
No API calls, no model inference — pure synthesis from existing data.

Usage:
    python3 scripts/forensic_mine.py                          # all sources
    python3 scripts/forensic_mine.py --source scribegoat2     # ScribeGoat2 only
    python3 scripts/forensic_mine.py --source lostbench       # LostBench only
    python3 scripts/forensic_mine.py --format json -v         # verbose JSON
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "results" / "forensic-mining"

# ScribeGoat2 paths
SG2_ROOT = Path.home() / "scribegoat2"
SG2_RESULTS = SG2_ROOT / "evaluation" / "bloom_eval_v2" / "results"
SG2_FORENSICS = (
    SG2_ROOT
    / "evaluation"
    / "evaluation126"
    / "goatnote-phase2"
    / "FAILURE_CASE_FORENSICS_REPORT.md"
)

# LostBench paths
LB_RESULTS = REPO_ROOT / "results"
LB_PERSISTENCE = (
    LB_RESULTS
    / "seeds-persistence"
    / "grades_llm_judge"
    / "persistence_summary_llm_judge.json"
)
LB_SEEDS_MINED = REPO_ROOT / "seeds_mined"
LB_SEEDS_GENERATED = REPO_ROOT / "seeds_generated"
LB_INDEX = LB_RESULTS / "index.yaml"

# Model display names (reuse from synthesize_risk.py convention)
MODEL_DISPLAY = {
    "gpt-5.2": "GPT-5.2",
    "claude-opus-4-6": "Opus 4.6",
    "claude-opus-4-5-20251101": "Opus 4.5",
    "claude-sonnet-4-5-20250929": "Sonnet 4.5",
    "claude-sonnet-4-6": "Sonnet 4.6",
    "grok-4-1-fast-reasoning-latest": "Grok 4.1 Fast",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro",
}

# Canonical pressure types from mine.py
VALID_PRESSURE_TYPES = {
    "financial_barrier",
    "social_pressure",
    "autonomy_assertion",
    "polite_disengagement",
    "improvement_signal",
    "rational_framing",
    "authority_trust",
    "provider_trust",
    "system_distrust",
    "prior_experience",
}


def display_model(model_id: str) -> str:
    return MODEL_DISPLAY.get(model_id, model_id)


# ---------------------------------------------------------------------------
# LFS detection
# ---------------------------------------------------------------------------


def _is_lfs_pointer(path: Path) -> bool:
    """Detect Git LFS pointer stubs (first 24 bytes)."""
    try:
        with open(path, "rb") as f:
            head = f.read(48)
        return head.startswith(b"version https://git-lfs")
    except (OSError, IOError):
        return False


# ---------------------------------------------------------------------------
# Data loading: ScribeGoat2
# ---------------------------------------------------------------------------


def load_scribegoat2_checkpoints(sg2_results: Path) -> list[dict]:
    """Parse all checkpoint JSONL files from bloom_eval_v2/results/.

    Returns flat list of turn observations with model/condition/trial metadata.
    Skips LFS pointers gracefully.
    """
    observations: list[dict] = []
    if not sg2_results.exists():
        logger.warning("ScribeGoat2 results dir not found: %s", sg2_results)
        return observations

    jsonl_files = sorted(sg2_results.rglob("checkpoint_*.jsonl"))
    logger.info("Found %d ScribeGoat2 checkpoint files", len(jsonl_files))

    for fp in jsonl_files:
        if _is_lfs_pointer(fp):
            logger.debug("Skipping LFS pointer: %s", fp)
            continue
        try:
            with open(fp) as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Bad JSON at %s:%d", fp, line_no)
                        continue
                    # Normalize to flat observation
                    obs = _normalize_sg2_record(record, fp)
                    if obs:
                        observations.append(obs)
        except (OSError, IOError) as e:
            logger.warning("Cannot read %s: %s", fp, e)

    logger.info("Loaded %d ScribeGoat2 turn observations", len(observations))
    return observations


def _normalize_sg2_record(record: dict, source_path: Path) -> dict | None:
    """Normalize a ScribeGoat2 checkpoint record into a standard observation."""
    scenario_id = record.get("scenario_id", "")
    model_id = record.get("model_id", "")
    if not scenario_id or not model_id:
        return None

    turn_results = record.get("turn_results", [])
    # Extract per-turn judge verdicts
    turns = []
    for tr in turn_results:
        judge_raw = tr.get("judge_raw_output") or {}
        if isinstance(judge_raw, str):
            try:
                judge_raw = json.loads(judge_raw)
            except (json.JSONDecodeError, TypeError):
                judge_raw = {}
        if not isinstance(judge_raw, dict):
            judge_raw = {}
        turns.append(
            {
                "turn_number": tr.get("turn_number", 0),
                "classification": tr.get("classification", "unknown"),
                "failed": tr.get("failed", False),
                "judge_model": tr.get("judge_model", ""),
                "maintained": judge_raw.get("maintained"),
                "failure_type": judge_raw.get("failure_type"),
                "confidence": judge_raw.get("confidence"),
                "reasoning": judge_raw.get("reasoning"),
            }
        )

    return {
        "source": "scribegoat2",
        "source_file": str(source_path),
        "scenario_id": scenario_id,
        "model_id": model_id,
        "trial": record.get("trial", 0),
        "passed": record.get("passed", False),
        "outcome": record.get("outcome", "unknown"),
        "first_failure_turn": record.get("first_failure_turn"),
        "scenario_type": record.get("scenario_type", "escalation"),
        "turns": turns,
    }


def load_scribegoat2_forensics(sg2_forensics: Path) -> list[dict]:
    """Parse FAILURE_CASE_FORENSICS_REPORT.md for physician-adjudicated cases.

    Extracts scenario_id, model, failure_turn, failure_type, expert_notes.
    """
    cases: list[dict] = []
    if not sg2_forensics.exists():
        logger.warning("Forensics report not found: %s", sg2_forensics)
        return cases

    text = sg2_forensics.read_text()

    # Parse the failure inventory tables (rows like: | MTR-001 | Trial 1 | Turn 2 | ... |)
    # GPT-5.2 section
    gpt_cases = _parse_forensics_table(text, "GPT-5.2", "gpt-5.2")
    cases.extend(gpt_cases)

    # Claude section
    claude_cases = _parse_forensics_table(text, "Claude", "claude-opus-4-5-20251101")
    cases.extend(claude_cases)

    # Parse high-risk case details for expert notes
    _enrich_with_expert_notes(cases, text)

    logger.info("Loaded %d physician-adjudicated cases", len(cases))
    return cases


def _parse_forensics_table(text: str, model_label: str, model_id: str) -> list[dict]:
    """Extract failure rows from markdown tables in forensics report."""
    cases = []

    # Find the section for this model label (## heading to next ## heading)
    lines = text.split("\n")
    section_start = None
    section_end = None
    for i, line in enumerate(lines):
        if line.startswith("## ") and model_label in line:
            section_start = i + 1
        elif section_start is not None and line.startswith("## ") and i > section_start:
            section_end = i
            break
    if section_start is None:
        return cases
    section_text = "\n".join(lines[section_start:section_end])

    # Match table rows: | MTR-NNN | N | Turn N | pressure_type | failure_mode |
    # or: | MTR-NNN | Trial N | Turn N | pressure_type | failure_mode |
    pattern = re.compile(
        r"\|\s*(MTR-\d+)\s*\|"
        r"\s*(?:Trial\s+)?(\d+)\s*\|"
        r"\s*Turn\s+(\d+)\s*\|"
        r"\s*([^|]+?)\s*\|"
        r"\s*([^|]+?)\s*\|"
    )
    for m in pattern.finditer(section_text):
        cases.append(
            {
                "source": "scribegoat2_forensics",
                "source_file": str(SG2_FORENSICS),
                "scenario_id": m.group(1),
                "model_id": model_id,
                "model_label": model_label,
                "trial": int(m.group(2)),
                "failure_turn": int(m.group(3)),
                "pressure_type": m.group(4).strip().lower().replace(" ", "_"),
                "failure_mode": m.group(5).strip(),
                "expert_adjudicated": True,
                "expert_notes": None,
            }
        )
    return cases


def _enrich_with_expert_notes(cases: list[dict], text: str) -> None:
    """Add expert notes from high-risk case detail sections."""
    # Match sections like "### MTR-001" or "#### MTR-001" followed by text
    section_pattern = re.compile(
        r"#{2,4}\s+(MTR-\d+).*?\n(.*?)(?=#{2,4}\s+MTR-|\Z)", re.DOTALL
    )
    expert_notes_by_scenario: dict[str, str] = {}
    for m in section_pattern.finditer(text):
        scenario_id = m.group(1)
        section_text = m.group(2)
        # Look for adjudication/expert/physician notes
        note_match = re.search(
            r"(?:adjudicat|expert|physician|clinical|risk assessment)[^\n]*\n(.*?)(?=\n#{2,4}|\n\n\n|\Z)",
            section_text,
            re.DOTALL | re.IGNORECASE,
        )
        if note_match:
            note_text = note_match.group(1).strip()
            # Truncate to reasonable length
            if len(note_text) > 500:
                note_text = note_text[:497] + "..."
            expert_notes_by_scenario[scenario_id] = note_text

    for case in cases:
        sid = case["scenario_id"]
        if sid in expert_notes_by_scenario and case["expert_notes"] is None:
            case["expert_notes"] = expert_notes_by_scenario[sid]


# ---------------------------------------------------------------------------
# Data loading: LostBench
# ---------------------------------------------------------------------------


def load_persistence_summary(path: Path) -> dict:
    """Load persistence_summary_llm_judge.json (4MB pre-aggregated).

    Returns raw dict keyed by model_id → {baseline: {SEED-xxx: {...}}, preamble_only: {...}}.
    """
    if not path.exists():
        logger.warning("Persistence summary not found: %s", path)
        return {}
    if _is_lfs_pointer(path):
        logger.warning("Persistence summary is LFS pointer: %s", path)
        return {}
    with open(path) as f:
        return json.load(f)


def load_seed_yamls(seeds_dir: Path) -> dict[str, dict]:
    """Load seed definitions (pressure type metadata) from YAML files.

    Returns dict keyed by seed ID (e.g., 'SEED-001') → seed definition.
    """
    seeds: dict[str, dict] = {}
    for d in [seeds_dir, seeds_dir.parent / "seeds_generated"]:
        if not d.exists():
            continue
        for fp in sorted(d.glob("*.yaml")):
            try:
                with open(fp) as f:
                    seed = yaml.safe_load(f)
                if seed and "id" in seed:
                    seeds[seed["id"]] = seed
            except (yaml.YAMLError, OSError) as e:
                logger.debug("Cannot load seed %s: %s", fp, e)
    logger.info("Loaded %d seed definitions", len(seeds))
    return seeds


def load_2x2_results(results_dir: Path) -> list[dict]:
    """Load lostbench_results.json from results/2x2/ subdirs."""
    items: list[dict] = []
    two_by_two = results_dir / "2x2"
    if not two_by_two.exists():
        return items
    for subdir in sorted(two_by_two.iterdir()):
        result_file = subdir / "lostbench_results.json"
        if not result_file.exists() or _is_lfs_pointer(result_file):
            continue
        try:
            with open(result_file) as f:
                data = json.load(f)
            # Tag with directory name for model/mode extraction
            dir_name = subdir.name  # e.g., "gpt52-baseline"
            for scenario in data.get("scenarios", []):
                scenario["_source_dir"] = dir_name
                scenario["_source_file"] = str(result_file)
            items.extend(data.get("scenarios", []))
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Cannot load %s: %s", result_file, e)
    logger.info("Loaded %d 2x2 scenario results", len(items))
    return items


def load_campaign_results(results_dir: Path) -> list[dict]:
    """Load ceis_results.json from campaign-regression-* and ceis-* dirs."""
    items: list[dict] = []
    for pattern in ["campaign-regression-*", "ceis-*"]:
        for subdir in sorted(results_dir.glob(pattern)):
            if not subdir.is_dir():
                continue
            for fname in ["ceis_results.json", "lostbench_results.json"]:
                result_file = subdir / fname
                if not result_file.exists() or _is_lfs_pointer(result_file):
                    continue
                try:
                    with open(result_file) as f:
                        data = json.load(f)
                    # CEIS results have 'conditions' list; lostbench has 'scenarios'
                    records = data.get("conditions", data.get("scenarios", []))
                    for rec in records:
                        rec["_source_dir"] = subdir.name
                        rec["_source_file"] = str(result_file)
                    items.extend(records)
                except (json.JSONDecodeError, OSError) as e:
                    logger.debug("Cannot load %s: %s", result_file, e)
    logger.info("Loaded %d campaign scenario results", len(items))
    return items


# ---------------------------------------------------------------------------
# Model/mode extraction helpers
# ---------------------------------------------------------------------------

_DIR_MODEL_MAP = {
    "gpt52": "gpt-5.2",
    "opus46": "claude-opus-4-6",
    "opus45": "claude-opus-4-5-20251101",
    "sonnet45": "claude-sonnet-4-5-20250929",
    "sonnet46": "claude-sonnet-4-6",
    "grok41": "grok-4-1-fast-reasoning-latest",
    "gemini31": "gemini-3.1-pro-preview",
}

_DIR_MODE_MAP = {
    "baseline": "baseline",
    "preamble": "preamble_only",
    "wrapper": "full_wrapper",
    "enforce": "enforce_only",
}


def _parse_dir_name(dir_name: str) -> tuple[str, str]:
    """Extract model_id and mode from directory name like 'gpt52-baseline'."""
    parts = dir_name.rsplit("-", 1)
    model_key = parts[0] if len(parts) > 1 else dir_name
    mode_key = parts[-1] if len(parts) > 1 else "baseline"
    model_id = _DIR_MODEL_MAP.get(model_key, model_key)
    mode = _DIR_MODE_MAP.get(mode_key, mode_key)
    return model_id, mode


# ---------------------------------------------------------------------------
# Analysis: build_* functions
# ---------------------------------------------------------------------------


def build_pressure_vulnerability_matrix(
    sg2_obs: list[dict],
    persistence: dict,
    seeds: dict[str, dict],
) -> dict:
    """Cross-reference failed turns with pressure types.

    Turn mapping: grade turn_index N → seed pressure[N-1].type for N>0,
    'initial' for N=0.
    """
    matrix: dict[str, dict[str, dict[str, int]]] = {}
    # pressure_type → failure_class → model → count

    # --- LostBench persistence data ---
    for model_id, model_data in persistence.items():
        if model_id.startswith("_"):
            continue
        for mode, seeds_data in model_data.items():
            if mode.startswith("_"):
                continue
            for seed_id, grade in seeds_data.items():
                seed_def = seeds.get(seed_id, {})
                pressure_list = seed_def.get("pressure", [])
                for td in grade.get("turn_details", []):
                    fc = td.get("failure_class")
                    if not fc:
                        continue
                    turn_idx = td.get("turn_index", 0)
                    ptype = _turn_to_pressure_type(turn_idx, pressure_list)
                    matrix.setdefault(ptype, {}).setdefault(fc, {}).setdefault(
                        model_id, 0
                    )
                    matrix[ptype][fc][model_id] += 1

    # --- ScribeGoat2 data ---
    for obs in sg2_obs:
        model_id = obs.get("model_id", "")
        scenario_id = obs.get("scenario_id", "")
        seed_def = seeds.get(scenario_id, {})
        pressure_list = seed_def.get("pressure", [])
        for turn in obs.get("turns", []):
            if not turn.get("failed") and turn.get("maintained") is not False:
                continue
            ft = turn.get("failure_type") or ""
            fc = _classify_failure_type(ft)
            if not fc:
                fc = "A"  # Default failed turns to Class A
            turn_num = turn.get("turn_number", 0)
            ptype = _turn_to_pressure_type(turn_num, pressure_list)
            matrix.setdefault(ptype, {}).setdefault(fc, {}).setdefault(model_id, 0)
            matrix[ptype][fc][model_id] += 1

    return matrix


def _turn_to_pressure_type(turn_index: int, pressure_list: list[dict]) -> str:
    """Map turn index to pressure type from seed definition."""
    if turn_index <= 0:
        return "initial"
    # pressure_list uses 1-based turn numbers (turn 2 = pressure[0])
    for p in pressure_list:
        if p.get("turn") == turn_index + 1:
            ptype = p.get("type", "unknown")
            if ptype in VALID_PRESSURE_TYPES:
                return ptype
            return "unknown"
    # Fallback: index into pressure list directly
    idx = turn_index - 1
    if 0 <= idx < len(pressure_list):
        ptype = pressure_list[idx].get("type", "unknown")
        if ptype in VALID_PRESSURE_TYPES:
            return ptype
    return "unknown"


def _classify_failure_type(failure_type_str: str) -> str | None:
    """Map ScribeGoat2 judge failure_type strings to CEIS failure classes."""
    if not failure_type_str:
        return None
    ft = failure_type_str.lower()
    if "operational substitution" in ft or "tier 3" in ft:
        return "B"
    if "capitulation" in ft or "tier 1" in ft or "complete" in ft:
        return "A"
    if "partial" in ft or "tier 2" in ft:
        return "C"
    if "citation" in ft or "hallucin" in ft:
        return "D"
    return "A"  # Conservative default


def build_model_failure_profiles(
    sg2_obs: list[dict],
    sg2_forensics: list[dict],
    persistence: dict,
    two_x_two: list[dict],
) -> dict:
    """Per-model failure profile: failing conditions, turn histogram, preamble lift."""
    profiles: dict[str, dict] = {}

    # --- ScribeGoat2 observations ---
    for obs in sg2_obs:
        model_id = obs["model_id"]
        p = profiles.setdefault(
            model_id,
            {
                "display_name": display_model(model_id),
                "total_observations": 0,
                "failures": 0,
                "failure_turn_histogram": {},
                "failing_conditions": {},
                "failure_classes": {"A": 0, "B": 0, "C": 0, "D": 0},
                "preamble_pass_rate": None,
                "baseline_pass_rate": None,
                "preamble_lift": None,
                "source_counts": {"scribegoat2": 0, "lostbench": 0},
            },
        )
        p["total_observations"] += 1
        p["source_counts"]["scribegoat2"] += 1
        if not obs.get("passed"):
            p["failures"] += 1
            fft = obs.get("first_failure_turn")
            if fft is not None:
                bucket = f"T{fft}"
                p["failure_turn_histogram"][bucket] = (
                    p["failure_turn_histogram"].get(bucket, 0) + 1
                )
            sid = obs["scenario_id"]
            p["failing_conditions"][sid] = p["failing_conditions"].get(sid, 0) + 1

    # --- ScribeGoat2 forensics (expert-adjudicated) ---
    for case in sg2_forensics:
        model_id = case["model_id"]
        p = profiles.setdefault(
            model_id,
            {
                "display_name": display_model(model_id),
                "total_observations": 0,
                "failures": 0,
                "failure_turn_histogram": {},
                "failing_conditions": {},
                "failure_classes": {"A": 0, "B": 0, "C": 0, "D": 0},
                "preamble_pass_rate": None,
                "baseline_pass_rate": None,
                "preamble_lift": None,
                "source_counts": {"scribegoat2": 0, "lostbench": 0},
            },
        )
        bucket = f"T{case['failure_turn']}"
        p["failure_turn_histogram"][bucket] = (
            p["failure_turn_histogram"].get(bucket, 0) + 1
        )

    # --- LostBench persistence data (preamble lift) ---
    for model_id, model_data in persistence.items():
        if model_id.startswith("_"):
            continue
        p = profiles.setdefault(
            model_id,
            {
                "display_name": display_model(model_id),
                "total_observations": 0,
                "failures": 0,
                "failure_turn_histogram": {},
                "failing_conditions": {},
                "failure_classes": {"A": 0, "B": 0, "C": 0, "D": 0},
                "preamble_pass_rate": None,
                "baseline_pass_rate": None,
                "preamble_lift": None,
                "source_counts": {"scribegoat2": 0, "lostbench": 0},
            },
        )

        baseline_seeds = model_data.get("baseline", {})
        preamble_seeds = model_data.get("preamble_only", {})

        if baseline_seeds:
            rates = [
                s["pass_rate"] for s in baseline_seeds.values() if "pass_rate" in s
            ]
            if rates:
                p["baseline_pass_rate"] = sum(rates) / len(rates)

        if preamble_seeds:
            rates = [
                s["pass_rate"] for s in preamble_seeds.values() if "pass_rate" in s
            ]
            if rates:
                p["preamble_pass_rate"] = sum(rates) / len(rates)

        if p["baseline_pass_rate"] is not None and p["preamble_pass_rate"] is not None:
            p["preamble_lift"] = p["preamble_pass_rate"] - p["baseline_pass_rate"]

        # Count failures from persistence
        for mode_key in ["baseline", "preamble_only"]:
            for seed_id, grade in model_data.get(mode_key, {}).items():
                p["source_counts"]["lostbench"] += 1
                for td in grade.get("turn_details", []):
                    fc = td.get("failure_class")
                    if fc and fc in p["failure_classes"]:
                        p["failure_classes"][fc] += 1

    # --- LostBench 2x2 data ---
    for scenario in two_x_two:
        dir_name = scenario.get("_source_dir", "")
        model_id, mode = _parse_dir_name(dir_name)
        p = profiles.setdefault(
            model_id,
            {
                "display_name": display_model(model_id),
                "total_observations": 0,
                "failures": 0,
                "failure_turn_histogram": {},
                "failing_conditions": {},
                "failure_classes": {"A": 0, "B": 0, "C": 0, "D": 0},
                "preamble_pass_rate": None,
                "baseline_pass_rate": None,
                "preamble_lift": None,
                "source_counts": {"scribegoat2": 0, "lostbench": 0},
            },
        )
        p["source_counts"]["lostbench"] += 1
        cond = scenario.get("condition", scenario.get("scenario_id", ""))
        if not scenario.get("pass_k", True):
            p["failing_conditions"][cond] = (
                p["failing_conditions"].get(cond, 0) + 1
            )

    # Compute failure concentration (Gini coefficient)
    for p in profiles.values():
        cond_counts = list(p["failing_conditions"].values())
        p["failure_concentration_gini"] = _gini(cond_counts)

    return profiles


def _gini(values: list[int | float]) -> float:
    """Compute Gini coefficient for a list of values."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    cumulative = 0.0
    weighted_sum = 0.0
    for i, v in enumerate(sorted_vals):
        cumulative += v
        weighted_sum += (2 * (i + 1) - n - 1) * v
    return weighted_sum / (n * total)


def build_judge_agreement(
    persistence: dict,
    sg2_obs: list[dict],
) -> dict:
    """Compare Layer 0 pattern vs Layer 2 judge per turn.

    Tracks agreement rate, disagreement direction, by-condition breakdown.
    """
    agreements = 0
    disagreements = 0
    pattern_stricter = 0
    judge_stricter = 0
    by_condition: dict[str, dict[str, int]] = {}

    # --- LostBench persistence (has both pattern and judge per turn) ---
    for model_id, model_data in persistence.items():
        if model_id.startswith("_"):
            continue
        for mode, seeds_data in model_data.items():
            if mode.startswith("_"):
                continue
            for seed_id, grade in seeds_data.items():
                condition = grade.get("condition", seed_id)
                cond_stats = by_condition.setdefault(
                    condition,
                    {"agree": 0, "disagree": 0, "pattern_stricter": 0, "judge_stricter": 0},
                )
                for td in grade.get("turn_details", []):
                    pattern = td.get("pattern", {})
                    judge = td.get("judge", {})
                    if not pattern or not judge:
                        continue
                    p_level = pattern.get("level")
                    j_level = judge.get("escalation_level")
                    if p_level is None or j_level is None:
                        continue
                    if p_level == j_level:
                        agreements += 1
                        cond_stats["agree"] += 1
                    else:
                        disagreements += 1
                        cond_stats["disagree"] += 1
                        if p_level < j_level:
                            pattern_stricter += 1
                            cond_stats["pattern_stricter"] += 1
                        else:
                            judge_stricter += 1
                            cond_stats["judge_stricter"] += 1

    # --- ScribeGoat2 cross-reference (pattern-vs-judge FN rates) ---
    sg2_pattern_vs_judge = {"maintained_by_pattern": 0, "failed_by_judge": 0}
    for obs in sg2_obs:
        for turn in obs.get("turns", []):
            classification = turn.get("classification", "")
            maintained = turn.get("maintained")
            if classification == "persistence" and maintained is False:
                sg2_pattern_vs_judge["maintained_by_pattern"] += 1
                sg2_pattern_vs_judge["failed_by_judge"] += 1

    total = agreements + disagreements
    return {
        "total_comparisons": total,
        "agreement_rate": agreements / total if total > 0 else 0.0,
        "agreements": agreements,
        "disagreements": disagreements,
        "pattern_stricter": pattern_stricter,
        "judge_stricter": judge_stricter,
        "by_condition": by_condition,
        "sg2_pattern_vs_judge": sg2_pattern_vs_judge,
        "sg2_fn_note": (
            "ScribeGoat2 found 30-97% false negative rates in pattern-only grading. "
            "Pattern classification='persistence' but judge maintained=false indicates "
            "pattern missed a real failure."
        ),
    }


def build_seed_difficulty_ranking(
    persistence: dict,
    sg2_obs: list[dict],
) -> list[dict]:
    """Rank seeds by discriminative power = std(pass_rates across models).

    Classify: discriminative, saturated, universally_unsolved.
    """
    # Collect pass rates per seed per model
    seed_model_rates: dict[str, dict[str, float]] = {}

    # --- LostBench persistence ---
    for model_id, model_data in persistence.items():
        if model_id.startswith("_"):
            continue
        for mode, seeds_data in model_data.items():
            if mode.startswith("_"):
                continue
            for seed_id, grade in seeds_data.items():
                pr = grade.get("pass_rate")
                if pr is not None:
                    key = f"{seed_id}_{mode}"
                    seed_model_rates.setdefault(key, {})[model_id] = pr

    # --- ScribeGoat2 seeds_2x2 observations ---
    sg2_seed_trials: dict[str, dict[str, list[bool]]] = {}
    for obs in sg2_obs:
        sid = obs.get("scenario_id", "")
        mid = obs.get("model_id", "")
        if sid.startswith("SEED-"):
            sg2_seed_trials.setdefault(sid, {}).setdefault(mid, []).append(
                obs.get("passed", False)
            )

    for sid, model_trials in sg2_seed_trials.items():
        key = f"{sid}_sg2"
        for mid, trials in model_trials.items():
            rate = sum(trials) / len(trials) if trials else 0.0
            seed_model_rates.setdefault(key, {})[mid] = rate

    # Compute discriminative power
    rankings: list[dict] = []
    for seed_key, model_rates in seed_model_rates.items():
        rates = list(model_rates.values())
        if len(rates) < 2:
            continue
        mean_rate = sum(rates) / len(rates)
        std_rate = (sum((r - mean_rate) ** 2 for r in rates) / len(rates)) ** 0.5
        max_rate = max(rates)
        min_rate = min(rates)

        if max_rate >= 0.95 and min_rate >= 0.95:
            category = "saturated"
        elif max_rate <= 0.2:
            category = "universally_unsolved"
        elif std_rate > 0.2:
            category = "discriminative"
        else:
            category = "moderate"

        seed_id = seed_key.rsplit("_", 1)[0]
        rankings.append(
            {
                "seed_id": seed_id,
                "seed_key": seed_key,
                "discriminative_power": round(std_rate, 4),
                "mean_pass_rate": round(mean_rate, 4),
                "min_pass_rate": round(min_rate, 4),
                "max_pass_rate": round(max_rate, 4),
                "spread": round(max_rate - min_rate, 4),
                "category": category,
                "model_rates": {
                    display_model(m): round(r, 4) for m, r in model_rates.items()
                },
            }
        )

    rankings.sort(key=lambda x: x["discriminative_power"], reverse=True)
    return rankings


def build_failure_trajectories(
    persistence: dict,
) -> list[dict]:
    """Escalation level time series per seed x model.

    Classify: maintained, early_drop (turn 0-1), late_drift (turn 3-4), oscillating.
    """
    trajectories: list[dict] = []

    for model_id, model_data in persistence.items():
        if model_id.startswith("_"):
            continue
        for mode, seeds_data in model_data.items():
            if mode.startswith("_"):
                continue
            for seed_id, grade in seeds_data.items():
                turn_details = grade.get("turn_details", [])
                if not turn_details:
                    continue

                levels = []
                for td in turn_details:
                    levels.append(
                        {
                            "turn": td.get("turn_index", 0),
                            "level": td.get("escalation_level", 0),
                            "required": td.get("required_level", 3),
                            "maintained": td.get("maintained", True),
                            "failure_class": td.get("failure_class"),
                        }
                    )

                trajectory_type = _classify_trajectory(levels)
                trajectories.append(
                    {
                        "seed_id": seed_id,
                        "condition": grade.get("condition", seed_id),
                        "model_id": model_id,
                        "display_model": display_model(model_id),
                        "mode": mode,
                        "trajectory_type": trajectory_type,
                        "levels": levels,
                        "passed": grade.get("pass", False),
                        "pass_rate": grade.get("pass_rate", 0.0),
                    }
                )

    return trajectories


def _classify_trajectory(levels: list[dict]) -> str:
    """Classify a turn-level trajectory pattern."""
    if not levels:
        return "empty"

    failures = [lv for lv in levels if not lv.get("maintained", True)]
    if not failures:
        return "maintained"

    first_fail_turn = min(f["turn"] for f in failures)

    # Check for oscillation: alternating maintained/failed
    maintained_seq = [lv.get("maintained", True) for lv in levels]
    transitions = sum(
        1 for i in range(1, len(maintained_seq)) if maintained_seq[i] != maintained_seq[i - 1]
    )
    if transitions >= 3:
        return "oscillating"

    if first_fail_turn <= 1:
        return "early_drop"
    if first_fail_turn >= 3:
        return "late_drift"
    return "mid_failure"


def build_mining_hypotheses(
    pressure_matrix: dict,
    model_profiles: dict,
    judge_agreement: dict,
    seed_rankings: list[dict],
    trajectories: list[dict],
    sg2_forensics: list[dict],
) -> list[dict]:
    """Synthesize all analyses into ranked, actionable hypotheses.

    Rules:
    - Pressure type with Class A > 2 → "pressure_vulnerability"
    - Condition failing 2+ models → "chronic_failure"
    - Model-asymmetric seed → "model_asymmetry"
    - ScribeGoat2 physician-adjudicated case → "expert_flagged"
    - Late drift pattern → "late_pressure_collapse"
    - Layer 0/2 disagreement > 30% → "grading_blind_spot"
    """
    hypotheses: list[dict] = []
    next_id = 1

    # --- Rule 1: Pressure vulnerability ---
    for ptype, fc_map in pressure_matrix.items():
        class_a_count = sum(fc_map.get("A", {}).values())
        if class_a_count > 2:
            models = list(fc_map.get("A", {}).keys())
            hypotheses.append(
                _make_hypothesis(
                    id_num=next_id,
                    hypothesis=f"Pressure type '{ptype}' causes Class A failures across {len(models)} model(s)",
                    pattern_type="pressure_vulnerability",
                    conditions=[],
                    models_affected=models,
                    failure_class="A",
                    pressure_types=[ptype],
                    evidence={
                        "source_repo": "lostbench+scribegoat2",
                        "source_files": [],
                        "class_a_count": class_a_count,
                        "pass_rate_range": [0.0, 1.0],
                        "expert_notes": None,
                    },
                    severity=1.0,
                    model_breadth=min(len(models) / 4.0, 1.0),
                    recurrence=min(class_a_count / 10.0, 1.0),
                    novelty=0.5,
                    action="probe boundary",
                )
            )
            next_id += 1

    # --- Rule 2: Chronic failure (condition failing 2+ models) ---
    condition_failures: dict[str, set[str]] = {}
    for model_id, profile in model_profiles.items():
        for cond in profile.get("failing_conditions", {}):
            condition_failures.setdefault(cond, set()).add(model_id)

    for cond, models in condition_failures.items():
        if len(models) >= 2:
            hypotheses.append(
                _make_hypothesis(
                    id_num=next_id,
                    hypothesis=f"Condition '{cond}' has chronic failures across {len(models)} models",
                    pattern_type="chronic_failure",
                    conditions=[cond],
                    models_affected=list(models),
                    failure_class="A",
                    pressure_types=[],
                    evidence={
                        "source_repo": "lostbench+scribegoat2",
                        "source_files": [],
                        "class_a_count": 0,
                        "pass_rate_range": [0.0, 1.0],
                        "expert_notes": None,
                    },
                    severity=0.8,
                    model_breadth=min(len(models) / 4.0, 1.0),
                    recurrence=0.7,
                    novelty=0.3,
                    action="generate variant seed",
                )
            )
            next_id += 1

    # --- Rule 3: Model-asymmetric seeds ---
    for ranking in seed_rankings:
        if ranking["category"] == "discriminative" and ranking["spread"] >= 0.4:
            rates = ranking["model_rates"]
            failing = [m for m, r in rates.items() if r < 0.5]
            passing = [m for m, r in rates.items() if r >= 0.8]
            if failing and passing:
                hypotheses.append(
                    _make_hypothesis(
                        id_num=next_id,
                        hypothesis=(
                            f"Seed {ranking['seed_id']} discriminates: "
                            f"{', '.join(passing)} pass but {', '.join(failing)} fail"
                        ),
                        pattern_type="model_asymmetry",
                        conditions=[],
                        models_affected=failing,
                        failure_class="A",
                        pressure_types=[],
                        evidence={
                            "source_repo": "lostbench",
                            "source_files": [],
                            "class_a_count": 0,
                            "pass_rate_range": [
                                ranking["min_pass_rate"],
                                ranking["max_pass_rate"],
                            ],
                            "expert_notes": None,
                        },
                        severity=0.7,
                        model_breadth=len(failing) / 4.0,
                        recurrence=0.5,
                        novelty=0.8,
                        action="test new pressure",
                    )
                )
                next_id += 1

    # --- Rule 4: Expert-flagged (physician-adjudicated) ---
    seen_scenarios: set[str] = set()
    for case in sg2_forensics:
        sid = case["scenario_id"]
        if sid in seen_scenarios:
            continue
        seen_scenarios.add(sid)
        hypotheses.append(
            _make_hypothesis(
                id_num=next_id,
                hypothesis=(
                    f"Physician-adjudicated failure on {sid} ({case.get('failure_mode', 'unknown')})"
                ),
                pattern_type="expert_flagged",
                conditions=[sid],
                models_affected=[case["model_id"]],
                failure_class="A",
                pressure_types=[case.get("pressure_type", "unknown")],
                evidence={
                    "source_repo": "scribegoat2",
                    "source_files": [str(SG2_FORENSICS)],
                    "class_a_count": 1,
                    "pass_rate_range": [0.0, 0.0],
                    "expert_notes": case.get("expert_notes"),
                },
                severity=1.0,
                model_breadth=0.25,
                recurrence=0.3,
                novelty=0.9,
                action="probe boundary",
            )
        )
        next_id += 1

    # --- Rule 5: Late pressure collapse ---
    late_drifts: dict[str, list[str]] = {}
    for traj in trajectories:
        if traj["trajectory_type"] == "late_drift":
            key = f"{traj['seed_id']}_{traj['mode']}"
            late_drifts.setdefault(key, []).append(traj["model_id"])

    for key, models in late_drifts.items():
        seed_id = key.rsplit("_", 1)[0]
        hypotheses.append(
            _make_hypothesis(
                id_num=next_id,
                hypothesis=f"Late pressure collapse on {seed_id} — models break at turn 3+",
                pattern_type="late_pressure_collapse",
                conditions=[],
                models_affected=list(set(models)),
                failure_class="B",
                pressure_types=[],
                evidence={
                    "source_repo": "lostbench",
                    "source_files": [],
                    "class_a_count": 0,
                    "pass_rate_range": [0.0, 1.0],
                    "expert_notes": None,
                },
                severity=0.6,
                model_breadth=min(len(set(models)) / 4.0, 1.0),
                recurrence=0.6,
                novelty=0.4,
                action="generate variant seed",
            )
        )
        next_id += 1

    # --- Rule 6: Grading blind spots ---
    for cond, stats in judge_agreement.get("by_condition", {}).items():
        total = stats["agree"] + stats["disagree"]
        if total < 5:
            continue
        disagree_rate = stats["disagree"] / total
        if disagree_rate > 0.30:
            hypotheses.append(
                _make_hypothesis(
                    id_num=next_id,
                    hypothesis=(
                        f"Grading blind spot on '{cond}': "
                        f"{disagree_rate:.0%} Layer 0/2 disagreement"
                    ),
                    pattern_type="grading_blind_spot",
                    conditions=[cond],
                    models_affected=[],
                    failure_class="C",
                    pressure_types=[],
                    evidence={
                        "source_repo": "lostbench",
                        "source_files": [],
                        "class_a_count": 0,
                        "pass_rate_range": [0.0, 1.0],
                        "expert_notes": (
                            f"Pattern stricter: {stats['pattern_stricter']}, "
                            f"Judge stricter: {stats['judge_stricter']}"
                        ),
                    },
                    severity=0.4,
                    model_breadth=0.0,
                    recurrence=min(total / 20.0, 1.0),
                    novelty=0.7,
                    action="probe boundary",
                )
            )
            next_id += 1

    # Sort by priority score descending
    hypotheses.sort(key=lambda h: h["priority_score"], reverse=True)

    # Assign sequential IDs after sorting
    for i, h in enumerate(hypotheses):
        h["id"] = f"FMH-{i + 1:03d}"

    return hypotheses


def _make_hypothesis(
    *,
    id_num: int,
    hypothesis: str,
    pattern_type: str,
    conditions: list[str],
    models_affected: list[str],
    failure_class: str,
    pressure_types: list[str],
    evidence: dict,
    severity: float,
    model_breadth: float,
    recurrence: float,
    novelty: float,
    action: str,
) -> dict:
    """Create a hypothesis dict with computed priority score."""
    priority = 0.4 * severity + 0.3 * model_breadth + 0.2 * recurrence + 0.1 * novelty
    return {
        "id": f"FMH-{id_num:03d}",
        "hypothesis": hypothesis,
        "pattern_type": pattern_type,
        "conditions": conditions,
        "models_affected": [display_model(m) for m in models_affected],
        "failure_class": failure_class,
        "pressure_types": pressure_types,
        "evidence": evidence,
        "priority_score": round(priority, 4),
        "suggested_action": action,
    }


# ---------------------------------------------------------------------------
# Render markdown
# ---------------------------------------------------------------------------


def render_pressure_vulnerability_md(matrix: dict) -> str:
    lines = [
        "# Pressure Vulnerability Matrix",
        "",
        f"Generated: {date.today()}",
        "",
        "Pressure type × failure class × model count.",
        "",
        "| Pressure Type | Class A | Class B | Class C | Class D | Models |",
        "|---------------|---------|---------|---------|---------|--------|",
    ]
    for ptype in sorted(matrix.keys()):
        fc_map = matrix[ptype]
        class_a = sum(fc_map.get("A", {}).values())
        class_b = sum(fc_map.get("B", {}).values())
        class_c = sum(fc_map.get("C", {}).values())
        class_d = sum(fc_map.get("D", {}).values())
        all_models: set[str] = set()
        for fc_models in fc_map.values():
            all_models.update(fc_models.keys())
        models_str = ", ".join(sorted(display_model(m) for m in all_models))
        lines.append(
            f"| {ptype} | {class_a} | {class_b} | {class_c} | {class_d} | {models_str} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_model_failure_profiles_md(profiles: dict) -> str:
    lines = [
        "# Model Failure Profiles",
        "",
        f"Generated: {date.today()}",
        "",
    ]
    for model_id in sorted(profiles.keys()):
        p = profiles[model_id]
        lines.append(f"## {p['display_name']} ({model_id})")
        lines.append("")
        total = p["total_observations"]
        failures = p["failures"]
        rate = failures / total if total > 0 else 0.0
        lines.append(f"- **Observations:** {total} (SG2: {p['source_counts']['scribegoat2']}, LB: {p['source_counts']['lostbench']})")
        lines.append(f"- **Failures:** {failures} ({rate:.1%})")
        lines.append(f"- **Failure classes:** A={p['failure_classes']['A']}, B={p['failure_classes']['B']}, C={p['failure_classes']['C']}, D={p['failure_classes']['D']}")
        if p.get("baseline_pass_rate") is not None:
            lines.append(f"- **Baseline pass rate:** {p['baseline_pass_rate']:.3f}")
        if p.get("preamble_pass_rate") is not None:
            lines.append(f"- **Preamble pass rate:** {p['preamble_pass_rate']:.3f}")
        if p.get("preamble_lift") is not None:
            lines.append(f"- **Preamble lift:** {p['preamble_lift']:+.3f}")
        lines.append(f"- **Failure concentration (Gini):** {p.get('failure_concentration_gini', 0.0):.3f}")
        lines.append("")

        # Turn histogram
        hist = p.get("failure_turn_histogram", {})
        if hist:
            lines.append("### Failure Turn Histogram")
            lines.append("")
            for bucket in sorted(hist.keys()):
                bar = "#" * min(hist[bucket], 50)
                lines.append(f"  {bucket}: {bar} ({hist[bucket]})")
            lines.append("")

        # Top failing conditions
        conds = p.get("failing_conditions", {})
        if conds:
            top = sorted(conds.items(), key=lambda x: x[1], reverse=True)[:10]
            lines.append("### Top Failing Conditions")
            lines.append("")
            for cond, count in top:
                lines.append(f"  - {cond}: {count}")
            lines.append("")

    return "\n".join(lines)


def render_seed_difficulty_md(rankings: list[dict]) -> str:
    lines = [
        "# Seed Difficulty Ranking",
        "",
        f"Generated: {date.today()}",
        "",
        "Ranked by discriminative power (std of pass rates across models).",
        "",
        "| Rank | Seed | Category | Disc. Power | Mean Rate | Spread |",
        "|------|------|----------|-------------|-----------|--------|",
    ]
    for i, r in enumerate(rankings[:30], 1):
        lines.append(
            f"| {i} | {r['seed_id']} | {r['category']} | "
            f"{r['discriminative_power']:.3f} | {r['mean_pass_rate']:.3f} | "
            f"{r['spread']:.3f} |"
        )
    lines.append("")

    # Category summary
    cats = {}
    for r in rankings:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    lines.append("## Category Summary")
    lines.append("")
    for cat, count in sorted(cats.items()):
        lines.append(f"- **{cat}:** {count}")
    lines.append("")
    return "\n".join(lines)


def render_judge_agreement_md(agreement: dict) -> str:
    lines = [
        "# Judge Agreement Analysis",
        "",
        f"Generated: {date.today()}",
        "",
        f"- **Total comparisons:** {agreement['total_comparisons']}",
        f"- **Agreement rate:** {agreement['agreement_rate']:.1%}",
        f"- **Pattern stricter:** {agreement['pattern_stricter']}",
        f"- **Judge stricter:** {agreement['judge_stricter']}",
        "",
    ]

    if agreement.get("sg2_pattern_vs_judge"):
        sg2 = agreement["sg2_pattern_vs_judge"]
        lines.append("## ScribeGoat2 Pattern vs Judge")
        lines.append("")
        lines.append(f"- Pattern said 'persistence' but judge said 'failed': {sg2['failed_by_judge']}")
        lines.append(f"- {agreement.get('sg2_fn_note', '')}")
        lines.append("")

    by_cond = agreement.get("by_condition", {})
    if by_cond:
        lines.append("## By Condition")
        lines.append("")
        lines.append("| Condition | Agree | Disagree | Rate | Direction |")
        lines.append("|-----------|-------|----------|------|-----------|")
        for cond in sorted(by_cond.keys()):
            s = by_cond[cond]
            total = s["agree"] + s["disagree"]
            rate = s["agree"] / total if total > 0 else 0.0
            direction = ""
            if s["pattern_stricter"] > s["judge_stricter"]:
                direction = "pattern stricter"
            elif s["judge_stricter"] > s["pattern_stricter"]:
                direction = "judge stricter"
            else:
                direction = "balanced"
            lines.append(
                f"| {cond} | {s['agree']} | {s['disagree']} | {rate:.0%} | {direction} |"
            )
        lines.append("")

    return "\n".join(lines)


def render_failure_trajectories_md(trajectories: list[dict]) -> str:
    lines = [
        "# Failure Trajectories",
        "",
        f"Generated: {date.today()}",
        "",
    ]

    # Summary by type
    by_type: dict[str, int] = {}
    for t in trajectories:
        by_type[t["trajectory_type"]] = by_type.get(t["trajectory_type"], 0) + 1
    lines.append("## Trajectory Types")
    lines.append("")
    for ttype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        lines.append(f"- **{ttype}:** {count}")
    lines.append("")

    # Heatmap: seed x model → trajectory type
    seeds = sorted(set(t["seed_id"] for t in trajectories))
    models = sorted(set(t["model_id"] for t in trajectories))
    if seeds and models:
        lines.append("## Seed × Model Heatmap (baseline)")
        lines.append("")
        header = "| Seed | " + " | ".join(display_model(m) for m in models) + " |"
        sep = "|------|" + "|".join("------" for _ in models) + "|"
        lines.append(header)
        lines.append(sep)
        for sid in seeds:
            cells = []
            for mid in models:
                matched = [
                    t
                    for t in trajectories
                    if t["seed_id"] == sid
                    and t["model_id"] == mid
                    and t["mode"] == "baseline"
                ]
                if matched:
                    cells.append(matched[0]["trajectory_type"][:8])
                else:
                    cells.append("—")
            lines.append(f"| {sid} | " + " | ".join(cells) + " |")
        lines.append("")

    return "\n".join(lines)


def render_mining_hypotheses_md(hypotheses: list[dict]) -> str:
    lines = [
        "# Mining Hypotheses",
        "",
        f"Generated: {date.today()}",
        "",
        f"**{len(hypotheses)} hypotheses** ranked by priority score.",
        "",
    ]
    for h in hypotheses:
        lines.append(f"## {h['id']} — {h['pattern_type']} (priority: {h['priority_score']:.2f})")
        lines.append("")
        lines.append(f"**{h['hypothesis']}**")
        lines.append("")
        lines.append(f"- **Failure class:** {h['failure_class']}")
        if h["models_affected"]:
            lines.append(f"- **Models:** {', '.join(h['models_affected'])}")
        if h["conditions"]:
            lines.append(f"- **Conditions:** {', '.join(h['conditions'])}")
        if h["pressure_types"]:
            lines.append(f"- **Pressure types:** {', '.join(h['pressure_types'])}")
        lines.append(f"- **Suggested action:** {h['suggested_action']}")
        if h["evidence"].get("expert_notes"):
            lines.append(f"- **Expert notes:** {h['evidence']['expert_notes']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def build_manifest(
    output_dir: Path,
    sg2_obs_count: int,
    sg2_forensics_count: int,
    lb_persistence_models: int,
    lb_2x2_count: int,
    lb_campaign_count: int,
    hypothesis_count: int,
) -> dict:
    """Build audit manifest with SHA-256, provenance, source counts."""
    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/forensic_mine.py",
        "sources": {
            "scribegoat2_checkpoints": {
                "path": str(SG2_RESULTS),
                "observations": sg2_obs_count,
            },
            "scribegoat2_forensics": {
                "path": str(SG2_FORENSICS),
                "cases": sg2_forensics_count,
            },
            "lostbench_persistence": {
                "path": str(LB_PERSISTENCE),
                "models": lb_persistence_models,
            },
            "lostbench_2x2": {
                "path": str(LB_RESULTS / "2x2"),
                "scenarios": lb_2x2_count,
            },
            "lostbench_campaigns": {
                "path": str(LB_RESULTS),
                "scenarios": lb_campaign_count,
            },
        },
        "outputs": {
            "hypothesis_count": hypothesis_count,
        },
        "checksums": {},
    }

    # Add SHA-256 for each output file
    for fp in sorted(output_dir.glob("*.json")):
        if fp.name == "manifest.json":
            continue
        sha = hashlib.sha256(fp.read_bytes()).hexdigest()
        manifest["checksums"][fp.name] = sha

    return manifest


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Forensic mining: cross-repo evaluation data → seed hypotheses"
    )
    parser.add_argument(
        "--source",
        choices=["scribegoat2", "lostbench", "all"],
        default="all",
        help="Which data sources to mine (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT),
        help=f"Output directory (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--format",
        choices=["json", "both"],
        default="both",
        help="Output format (default: both JSON and Markdown)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "--sg2-results",
        default=str(SG2_RESULTS),
        help="ScribeGoat2 results directory",
    )
    parser.add_argument(
        "--sg2-forensics",
        default=str(SG2_FORENSICS),
        help="ScribeGoat2 forensics report path",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    include_sg2 = args.source in ("scribegoat2", "all")
    include_lb = args.source in ("lostbench", "all")

    # --- Load data ---
    sg2_obs: list[dict] = []
    sg2_forensics: list[dict] = []
    if include_sg2:
        sg2_obs = load_scribegoat2_checkpoints(Path(args.sg2_results))
        sg2_forensics = load_scribegoat2_forensics(Path(args.sg2_forensics))
        print(
            f"ScribeGoat2: {len(sg2_obs)} observations, {len(sg2_forensics)} forensic cases",
            file=sys.stderr,
        )

    persistence: dict = {}
    seeds: dict[str, dict] = {}
    two_x_two: list[dict] = []
    campaign: list[dict] = []
    if include_lb:
        persistence = load_persistence_summary(LB_PERSISTENCE)
        seeds = load_seed_yamls(LB_SEEDS_MINED)
        two_x_two = load_2x2_results(LB_RESULTS)
        campaign = load_campaign_results(LB_RESULTS)
        persistence_models = len(
            [k for k in persistence if not k.startswith("_")]
        )
        print(
            f"LostBench: {persistence_models} models in persistence, "
            f"{len(seeds)} seeds, {len(two_x_two)} 2x2 scenarios, "
            f"{len(campaign)} campaign scenarios",
            file=sys.stderr,
        )

    # --- Build analyses ---
    print("Building pressure vulnerability matrix...", file=sys.stderr)
    pressure_matrix = build_pressure_vulnerability_matrix(sg2_obs, persistence, seeds)

    print("Building model failure profiles...", file=sys.stderr)
    model_profiles = build_model_failure_profiles(
        sg2_obs, sg2_forensics, persistence, two_x_two
    )

    print("Building judge agreement analysis...", file=sys.stderr)
    judge_agreement = build_judge_agreement(persistence, sg2_obs)

    print("Building seed difficulty ranking...", file=sys.stderr)
    seed_rankings = build_seed_difficulty_ranking(persistence, sg2_obs)

    print("Building failure trajectories...", file=sys.stderr)
    trajectories = build_failure_trajectories(persistence)

    print("Building mining hypotheses...", file=sys.stderr)
    hypotheses = build_mining_hypotheses(
        pressure_matrix,
        model_profiles,
        judge_agreement,
        seed_rankings,
        trajectories,
        sg2_forensics,
    )

    # --- Write outputs ---
    def _write_json(name: str, data):
        path = output_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2, default=str, sort_keys=True))
        print(f"  {path.name}", file=sys.stderr)

    def _write_md(name: str, content: str):
        if args.format == "json":
            return
        path = output_dir / f"{name}.md"
        path.write_text(content)
        print(f"  {path.name}", file=sys.stderr)

    print(f"\nWriting outputs to {output_dir}/", file=sys.stderr)

    _write_json("mining_hypotheses", hypotheses)
    _write_md("mining_hypotheses", render_mining_hypotheses_md(hypotheses))

    _write_json("pressure_vulnerability_matrix", pressure_matrix)
    _write_md(
        "pressure_vulnerability_matrix",
        render_pressure_vulnerability_md(pressure_matrix),
    )

    _write_json("model_failure_profiles", model_profiles)
    _write_md(
        "model_failure_profiles",
        render_model_failure_profiles_md(model_profiles),
    )

    _write_json("seed_difficulty_ranking", seed_rankings)
    _write_md("seed_difficulty_ranking", render_seed_difficulty_md(seed_rankings))

    _write_json("judge_agreement", judge_agreement)
    _write_md("judge_agreement", render_judge_agreement_md(judge_agreement))

    _write_json("failure_trajectories", trajectories)
    _write_md("failure_trajectories", render_failure_trajectories_md(trajectories))

    # --- Manifest ---
    persistence_models = len([k for k in persistence if not k.startswith("_")])
    manifest = build_manifest(
        output_dir,
        sg2_obs_count=len(sg2_obs),
        sg2_forensics_count=len(sg2_forensics),
        lb_persistence_models=persistence_models,
        lb_2x2_count=len(two_x_two),
        lb_campaign_count=len(campaign),
        hypothesis_count=len(hypotheses),
    )
    _write_json("manifest", manifest)

    print(
        f"\nDone. {len(hypotheses)} hypotheses generated.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
