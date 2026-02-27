"""Re-grade existing 50-scenario emergency results with the live LLM judge.

The original CEIS grading in cli.py never wired up the LLM judge (judge_fn was
not passed to grade_corpus_multi_trial). This script reads cached model responses
from lostbench_results.json or checkpoint files and re-grades them through the
full 3-layer CEIS pipeline with the cross-vendor LLM judge.

Usage:
    # Source API keys first
    set -a && source .env && set +a

    # Re-grade all available 50-scenario results
    python scripts/regrade_50_with_judge.py

    # Re-grade a specific result
    python scripts/regrade_50_with_judge.py --only grok
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lostbench.ceis import grade_corpus_multi_trial
from lostbench.ceis_config import CEISConfig
from lostbench.ceis_report import generate_ceis_json, generate_executive_summary
from lostbench.judge import call_escalation_judge
from lostbench.scenarios.loader import load_scenarios


# Results to re-grade: (label, model, provider, judge_model, source_type, source_path, output_dir)
ENTRIES = [
    {
        "label": "grok",
        "model": "grok-4-1-fast-reasoning-latest",
        "provider": "xai",
        "judge_model": "claude-opus-4-6",
        "judge_provider": "anthropic",
        "source": "results/ceis-emergency-grok41r-n3/lostbench_results.json",
        "source_type": "results",
        "output_dir": "results/ceis-emergency-grok41r-n3",
    },
    {
        "label": "gemini",
        "model": "gemini-3.1-pro-preview",
        "provider": "google",
        "judge_model": "claude-opus-4-6",
        "judge_provider": "anthropic",
        "source": "results/ceis-emergency-gemini31pro-n3/.lostbench_checkpoint.json",
        "source_type": "checkpoint",
        "output_dir": "results/ceis-emergency-gemini31pro-n3",
    },
]


def extract_responses_from_results(path: str) -> dict[str, list[list[str]]]:
    """Extract per-trial assistant responses from lostbench_results.json."""
    with open(path) as f:
        data = json.load(f)

    all_trial_responses: dict[str, list[list[str]]] = {}
    for s in data.get("scenarios", []):
        sid = s["scenario_id"]
        trial_responses: list[list[str]] = []
        for trial in s.get("per_trial", []):
            conv = trial.get("conversation", [])
            responses = [m["content"] for m in conv if m.get("role") == "assistant"]
            trial_responses.append(responses)
        if trial_responses:
            all_trial_responses[sid] = trial_responses

    return all_trial_responses


def extract_responses_from_checkpoint(path: str) -> dict[str, list[list[str]]]:
    """Extract per-trial assistant responses from checkpoint file."""
    with open(path) as f:
        data = json.load(f)

    all_trial_responses: dict[str, list[list[str]]] = {}
    for s in data.get("scenario_results", []):
        sid = s["scenario_id"]
        trial_responses: list[list[str]] = []
        for trial in s.get("per_trial", []):
            conv = trial.get("conversation", [])
            responses = [m["content"] for m in conv if m.get("role") == "assistant"]
            trial_responses.append(responses)
        if trial_responses:
            all_trial_responses[sid] = trial_responses

    return all_trial_responses


def build_judge_fn(judge_provider_name: str, judge_model: str):
    """Build a live LLM judge function using the specified provider."""
    from lostbench.providers import get_provider

    provider = get_provider(judge_provider_name)

    async def judge_fn(response: str, scenario: dict | None = None):
        return await call_escalation_judge(
            provider, response, judge_model, scenario=scenario
        )

    return judge_fn


def regrade_entry(entry: dict, scenarios: list[dict]) -> dict | None:
    """Re-grade a single result through CEIS with the live LLM judge."""
    repo_root = Path(__file__).resolve().parent.parent
    source_path = repo_root / entry["source"]

    if not source_path.exists():
        print(f"  SKIP (not found): {entry['source']}")
        return None

    # Extract responses
    if entry["source_type"] == "results":
        all_trial_responses = extract_responses_from_results(str(source_path))
    else:
        all_trial_responses = extract_responses_from_checkpoint(str(source_path))

    if not all_trial_responses:
        print(f"  SKIP (no responses): {entry['source']}")
        return None

    # Filter to only scenarios in the first 50 (MTR-001 through MTR-050)
    orig_50_ids = {f"MTR-{i:03d}" for i in range(1, 51)}
    all_trial_responses = {
        sid: trials
        for sid, trials in all_trial_responses.items()
        if sid in orig_50_ids
    }
    scenarios_50 = [s for s in scenarios if s["id"] in orig_50_ids]

    n_trials = max((len(v) for v in all_trial_responses.values()), default=1)
    print(f"  {len(all_trial_responses)} scenarios, {n_trials} trials each")

    # Build live judge
    judge_fn = build_judge_fn(entry["judge_provider"], entry["judge_model"])

    # Grade with live judge
    corpus_grade = asyncio.run(
        grade_corpus_multi_trial(scenarios_50, all_trial_responses, judge_fn=judge_fn)
    )

    # Build config for report
    model_short = entry["model"][:30]
    run_id = f"EG-{model_short.replace('/', '-')[:20]}-50regrade"

    config = CEISConfig(
        model=entry["model"],
        provider=entry["provider"],
        n_trials=n_trials,
        corpus="emergency",
    )

    # Generate artifacts
    artifact = generate_ceis_json(config, corpus_grade, run_id=run_id)
    summary = generate_executive_summary(config, corpus_grade, run_id=run_id)

    # Write to output dir
    out_dir = Path(repo_root / entry["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "ceis_results.json", "w") as f:
        json.dump(artifact, f, indent=2)
    (out_dir / "ceis_report.txt").write_text(summary)

    print(summary)

    return {
        "label": entry["label"],
        "model": entry["model"],
        "pass_k": corpus_grade.pass_k,
        "ers": corpus_grade.ers,
        "ers_ci": corpus_grade.ers_bootstrap_ci,
        "class_a": corpus_grade.total_classA,
        "class_d": corpus_grade.total_classD,
        "layer_0_pct": corpus_grade.grading_metadata.get("layer_0_pct", 0),
        "layer_2_pct": corpus_grade.grading_metadata.get("layer_2_pct", 0),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Re-grade 50-scenario emergency results with live LLM judge"
    )
    parser.add_argument(
        "--only",
        choices=["grok", "gemini"],
        help="Re-grade only a specific model",
    )
    args = parser.parse_args()

    scenarios = load_scenarios("emergency")
    print(f"Loaded {len(scenarios)} scenarios from emergency corpus\n")

    entries = ENTRIES
    if args.only:
        entries = [e for e in entries if e["label"] == args.only]

    results = []
    for entry in entries:
        print(f"=== Re-grading: {entry['label']} ({entry['model']}) ===")
        r = regrade_entry(entry, scenarios)
        if r:
            results.append(r)
        print()

    if results:
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        for r in results:
            print(
                f"  {r['label']:10s}  Pass^k={r['pass_k']:.3f}  ERS={r['ers']}  "
                f"ClassA={r['class_a']}  ClassD={r['class_d']}  "
                f"L0={r['layer_0_pct']:.1f}%  L2={r['layer_2_pct']:.1f}%"
            )


if __name__ == "__main__":
    main()
