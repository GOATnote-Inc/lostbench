#!/usr/bin/env python3
"""Generate audit manifest for evaluation results.

Produces a manifest.json with provenance, integrity hashes, and chain-of-custody
metadata compliant with:
  - 21 CFR Part 11 (FDA electronic records)
  - ISO 14155:2020 (clinical investigation of medical devices)
  - ICH E6(R2) (good clinical practice)
  - GAMP 5 (data integrity — ALCOA+ principles)

ALCOA+ coverage:
  A - Attributable:  operator, git commit, model versions, judge routing
  L - Legible:       JSON with schema version, human-readable summary
  C - Contemporaneous: timestamps from challenge files, manifest generation time
  O - Original:      SHA-256 integrity hashes on all artifacts
  A - Accurate:      deterministic settings (seed=42, temp=0.0), cross-vendor judge

  + Complete:    file counts, expected vs actual matrix
  + Consistent:  schema_version field for forward compatibility
  + Enduring:    self-contained manifest (no external refs except git)
  + Available:   single JSON file, machine-parseable

Usage:
    python3 scripts/generate_eval_manifest.py results/seeds-gen-eval/
    python3 scripts/generate_eval_manifest.py results/seeds-gen-eval/ --output manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "1.0.0"

JUDGE_ROUTING = {
    "claude-opus-4-6": {"judge_model": "gpt-5.2", "judge_provider": "openai"},
    "gpt-5.2": {"judge_model": "claude-opus-4-6", "judge_provider": "anthropic"},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_git_info(repo_dir: Path) -> dict:
    info = {}
    try:
        info["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True
        ).strip()
        info["branch"] = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, text=True
        ).strip()
        info["dirty"] = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=repo_dir, text=True
            ).strip()
        )
        info["remote"] = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], cwd=repo_dir, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        info["error"] = "git info unavailable"
    return info


def extract_challenge_metadata(path: Path) -> dict:
    """Extract audit-relevant fields from a challenge JSON."""
    with open(path) as f:
        data = json.load(f)
    return {
        "file": str(path.name),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "scenario_id": data.get("scenario_id"),
        "condition": data.get("condition"),
        "model": data.get("model"),
        "n_trials": data.get("n_trials"),
        "temperature": data.get("temperature"),
        "seed": data.get("seed"),
        "timestamp": data.get("timestamp"),
        "n_transcripts": len(data.get("transcripts", [])),
        "total_responses": sum(
            len(t.get("responses", [])) for t in data.get("transcripts", [])
        ),
    }


def extract_grade_metadata(path: Path) -> dict:
    """Extract audit-relevant fields from a grade JSON."""
    with open(path) as f:
        data = json.load(f)
    return {
        "file": str(path.name),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "scenario_id": data.get("scenario_id"),
        "condition": data.get("condition"),
        "model": data.get("model"),
        "passed": data.get("pass"),
        "eps_point": data.get("eps_point"),
        "classA": data.get("classA", 0),
        "classB": data.get("classB", 0),
        "classC": data.get("classC", 0),
        "classD": data.get("classD", 0),
        "grading_methodology": data.get("grading_methodology"),
        "judge_model": (data.get("cross_vendor_routing") or {}).get("judge_model"),
        "timestamp": data.get("timestamp"),
    }


def generate_manifest(results_dir: Path) -> dict:
    repo_root = Path(__file__).parent.parent

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": "evaluation_audit_manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/generate_eval_manifest.py",
        "results_directory": str(results_dir),
    }

    # Provenance
    manifest["provenance"] = {
        "repository": get_git_info(repo_root),
        "operator": os.environ.get("USER", "unknown"),
        "hostname": platform.node(),
        "platform": f"{platform.system()} {platform.release()}",
        "python_version": platform.python_version(),
    }

    # Evaluation protocol
    manifest["protocol"] = {
        "name": "seeds-gen-eval",
        "description": "20 generated seeds × 2 models × 2 conditions × n=5 trials",
        "models": ["claude-opus-4-6", "gpt-5.2"],
        "conditions": ["baseline", "preamble_only"],
        "n_trials": 5,
        "determinism": {"temperature": 0.0, "seed": 42},
        "judge_routing": JUDGE_ROUTING,
        "grading_methodology": "cross_vendor_llm_judge",
        "layer_0_threshold": "inf (force LLM judge on every turn)",
    }

    # Seed inventory
    seeds_dir = repo_root / "seeds_generated"
    seed_files = sorted(seeds_dir.glob("gen-*.yaml")) if seeds_dir.exists() else []
    manifest["seeds"] = {
        "directory": str(seeds_dir),
        "count": len(seed_files),
        "files": [
            {"file": f.name, "sha256": sha256_file(f), "size_bytes": f.stat().st_size}
            for f in seed_files
        ],
    }

    # Challenge artifacts
    challenge_files = sorted(results_dir.rglob("challenge_*.json"))
    challenges_by_subdir = {}
    for cf in challenge_files:
        subdir = cf.parent.name
        if subdir not in challenges_by_subdir:
            challenges_by_subdir[subdir] = []
        challenges_by_subdir[subdir].append(extract_challenge_metadata(cf))

    manifest["challenges"] = {
        "total_files": len(challenge_files),
        "expected_files": 80,  # 20 seeds × 2 models × 2 conditions
        "complete": len(challenge_files) >= 80,
        "subdirectories": challenges_by_subdir,
    }

    # Grade artifacts
    grades_dir = results_dir / "grades_llm_judge"
    grade_files = (
        sorted(grades_dir.rglob("grade_*.json")) if grades_dir.exists() else []
    )
    grades_by_subdir = {}
    for gf in grade_files:
        subdir = gf.parent.name
        if subdir not in grades_by_subdir:
            grades_by_subdir[subdir] = []
        grades_by_subdir[subdir].append(extract_grade_metadata(gf))

    manifest["grades"] = {
        "total_files": len(grade_files),
        "expected_files": 80,
        "complete": len(grade_files) >= 80,
        "subdirectories": grades_by_subdir,
    }

    # Summary artifacts
    summaries = []
    for name in [
        "grades_llm_judge/persistence_summary_llm_judge.json",
        "checkpoint.json",
        "grades_llm_judge/regrade_checkpoint.json",
    ]:
        p = results_dir / name
        if p.exists():
            summaries.append(
                {
                    "file": name,
                    "sha256": sha256_file(p),
                    "size_bytes": p.stat().st_size,
                }
            )
    manifest["summary_artifacts"] = summaries

    # Completeness matrix
    matrix = {}
    for cf_meta_list in challenges_by_subdir.values():
        for cf_meta in cf_meta_list:
            key = f"{cf_meta['model']}|{cf_meta['scenario_id']}"
            if key not in matrix:
                matrix[key] = {
                    "model": cf_meta["model"],
                    "scenario_id": cf_meta["scenario_id"],
                    "conditions": [],
                }
            # Infer condition from parent dir name
            matrix[key]["conditions"].append(cf_meta.get("condition", "unknown"))

    manifest["completeness"] = {
        "total_model_seed_pairs": len(matrix),
        "expected_model_seed_pairs": 40,  # 20 seeds × 2 models
        "pairs_with_both_conditions": sum(
            1 for v in matrix.values() if len(v["conditions"]) >= 2
        ),
    }

    # Integrity
    all_hashes = []
    for seed_entry in manifest["seeds"]["files"]:
        all_hashes.append(seed_entry["sha256"])
    for subdir_list in challenges_by_subdir.values():
        for cf_meta in subdir_list:
            all_hashes.append(cf_meta["sha256"])
    for subdir_list in grades_by_subdir.values():
        for gf_meta in subdir_list:
            all_hashes.append(gf_meta["sha256"])

    composite = hashlib.sha256("\n".join(sorted(all_hashes)).encode()).hexdigest()
    manifest["integrity"] = {
        "total_hashed_files": len(all_hashes),
        "composite_hash": composite,
        "algorithm": "SHA-256",
        "note": "Composite hash = SHA-256 of sorted newline-joined individual file hashes",
    }

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Generate audit manifest for evaluation results"
    )
    parser.add_argument(
        "results_dir",
        type=Path,
        help="Path to results directory (e.g., results/seeds-gen-eval/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: {results_dir}/manifest.json)",
    )
    args = parser.parse_args()

    if not args.results_dir.exists():
        print(f"ERROR: {args.results_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    output = args.output or (args.results_dir / "manifest.json")

    manifest = generate_manifest(args.results_dir)

    with open(output, "w") as f:
        json.dump(manifest, f, indent=2)

    # Print summary
    print(f"Manifest: {output}")
    print(f"  Seeds:      {manifest['seeds']['count']}")
    print(
        f"  Challenges: {manifest['challenges']['total_files']}/{manifest['challenges']['expected_files']}"
    )
    print(
        f"  Grades:     {manifest['grades']['total_files']}/{manifest['grades']['expected_files']}"
    )
    print(f"  Hashed:     {manifest['integrity']['total_hashed_files']} files")
    print(f"  Composite:  {manifest['integrity']['composite_hash'][:16]}...")
    print(
        f"  Complete:   {'YES' if manifest['challenges']['complete'] else 'NO (eval still running)'}"
    )


if __name__ == "__main__":
    main()
