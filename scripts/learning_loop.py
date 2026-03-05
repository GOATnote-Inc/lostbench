#!/usr/bin/env python3
"""Learning Loop Orchestrator.

End-to-end: re-mine → hypotheses → scenarios → challenges → grades → family proposals.

Two modes:
  --dry-run ($0): generates hypotheses only, no API calls. Suitable for daily cadence.
  Full mode: calls lostbench mine, challenge, grade in sequence.

Usage:
    python3 scripts/learning_loop.py --dry-run --models gpt-5.2
    python3 scripts/learning_loop.py --models gpt-5.2 --max-cost-usd 25
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = REPO_ROOT / "results" / "analysis"
PRICING_PATH = REPO_ROOT / "configs" / "model_pricing.yaml"
FAMILIES_PATH = REPO_ROOT / "configs" / "exploit_families.yaml"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def load_pricing(path: Path) -> dict:
    """Load model pricing config."""
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def estimate_cost(
    pricing: dict,
    models: list[str],
    n_scenarios: int,
    n_trials: int,
) -> float:
    """Estimate API cost in USD."""
    total = 0.0
    model_configs = pricing.get("models", {})
    for model in models:
        cfg = model_configs.get(model, {})
        input_per_1m = cfg.get("input_per_1m", 5.0)
        output_per_1m = cfg.get("output_per_1m", 15.0)
        avg_tokens = cfg.get("avg_tokens_per_challenge", 4000)
        cost = (
            n_scenarios
            * n_trials
            * avg_tokens
            * (input_per_1m + output_per_1m)
            / 1_000_000
        )
        total += cost
    return total


def run_command(cmd: list[str], description: str) -> subprocess.CompletedProcess:
    """Run a subprocess command with logging."""
    print(f"  [{description}] {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:500]}", file=sys.stderr)
    return result


def run_hypotheses(analysis_dir: Path, output_dir: Path) -> Path:
    """Run generate_hypotheses.py."""
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "generate_hypotheses.py"),
        "--analysis-dir",
        str(analysis_dir),
        "--output-dir",
        str(output_dir),
    ]
    run_command(cmd, "generate hypotheses")
    return output_dir / "hypotheses.json"


def run_family_proposals(analysis_dir: Path, output_dir: Path) -> Path:
    """Run propose_exploit_families.py."""
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "propose_exploit_families.py"),
        "--analysis-dir",
        str(analysis_dir),
        "--output-dir",
        str(output_dir),
    ]
    run_command(cmd, "propose families")
    return output_dir / "proposed_families.yaml"


def main():
    parser = argparse.ArgumentParser(
        description="Learning loop orchestrator: mine → hypotheses → challenge → grade → propose"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate hypotheses only, no API calls ($0 cost)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["gpt-5.2"],
        help="Models to test (default: gpt-5.2)",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        default=None,
        help="Providers (auto-detected from model_pricing.yaml if omitted)",
    )
    parser.add_argument(
        "--max-hypotheses",
        type=int,
        default=10,
        help="Max hypotheses to test (default: 10)",
    )
    parser.add_argument(
        "--scenarios-per-hypothesis",
        type=int,
        default=3,
        help="Scenarios generated per hypothesis (default: 3)",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=5,
        help="Trials per scenario (default: 5)",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=50.0,
        help="Maximum estimated cost in USD (default: 50)",
    )
    parser.add_argument(
        "--analysis-dir",
        default=str(ANALYSIS_DIR),
        help="Analysis directory",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: results/loop-<date>/)",
    )
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = REPO_ROOT / "results" / f"loop-{timestamp}"

    output_dir.mkdir(parents=True, exist_ok=True)

    pricing = load_pricing(PRICING_PATH)

    # Auto-detect providers
    if args.providers:
        providers = dict(zip(args.models, args.providers))
    else:
        model_configs = pricing.get("models", {})
        providers = {}
        for m in args.models:
            cfg = model_configs.get(m, {})
            providers[m] = cfg.get("provider", "openai")

    print(f"Learning loop started at {timestamp}", file=sys.stderr)
    print(f"Models: {args.models}", file=sys.stderr)
    print(f"Dry run: {args.dry_run}", file=sys.stderr)
    print(f"Output: {output_dir}", file=sys.stderr)

    # Step 1: Generate hypotheses ($0)
    print("\n--- Step 1: Generate Hypotheses ---", file=sys.stderr)
    hypotheses_path = run_hypotheses(analysis_dir, output_dir)

    hypotheses = []
    if hypotheses_path.exists():
        with open(hypotheses_path) as f:
            hypotheses = json.load(f)
    print(f"Generated {len(hypotheses)} hypotheses", file=sys.stderr)

    # Step 2: Generate family proposals ($0)
    print("\n--- Step 2: Propose Exploit Families ---", file=sys.stderr)
    proposals_path = run_family_proposals(analysis_dir, output_dir)
    print(f"Family proposals: {proposals_path}", file=sys.stderr)

    # Step 3: Budget check
    top_hypotheses = hypotheses[: args.max_hypotheses]
    n_scenarios = len(top_hypotheses) * args.scenarios_per_hypothesis
    estimated_cost = estimate_cost(pricing, args.models, n_scenarios, args.n_trials)

    print("\n--- Budget Estimate ---", file=sys.stderr)
    print(f"Hypotheses to test: {len(top_hypotheses)}", file=sys.stderr)
    print(f"Scenarios to generate: {n_scenarios}", file=sys.stderr)
    print(f"Estimated cost: ${estimated_cost:.2f}", file=sys.stderr)
    print(f"Budget limit: ${args.max_cost_usd:.2f}", file=sys.stderr)

    if args.dry_run:
        summary = {
            "mode": "dry_run",
            "timestamp": timestamp,
            "hypotheses_generated": len(hypotheses),
            "top_hypotheses": len(top_hypotheses),
            "estimated_scenarios": n_scenarios,
            "estimated_cost_usd": round(estimated_cost, 2),
            "models": args.models,
            "family_proposals": str(proposals_path),
        }
        (output_dir / "loop_summary.json").write_text(json.dumps(summary, indent=2))
        print(
            f"\nDry run complete. Summary: {output_dir / 'loop_summary.json'}",
            file=sys.stderr,
        )
        return

    # Budget gate
    if estimated_cost > args.max_cost_usd:
        print(
            f"\nBLOCK: Estimated cost ${estimated_cost:.2f} exceeds "
            f"budget ${args.max_cost_usd:.2f}. Use --max-cost-usd to increase.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 4: Generate scenarios from hypotheses
    print("\n--- Step 4: Generate Scenarios ---", file=sys.stderr)
    mined_dir = output_dir / "mined"
    mined_dir.mkdir(exist_ok=True)
    scenarios_generated = 0

    for i, h in enumerate(top_hypotheses):
        hyp_str = h["hypothesis"][:300]
        cmd = [
            "lostbench",
            "mine",
            "--hypothesis",
            hyp_str,
            "--output-dir",
            str(mined_dir),
            "--count",
            str(args.scenarios_per_hypothesis),
        ]
        result = run_command(cmd, f"mine hypothesis {i + 1}/{len(top_hypotheses)}")
        if result.returncode == 0:
            scenarios_generated += args.scenarios_per_hypothesis

    print(f"Scenarios generated: ~{scenarios_generated}", file=sys.stderr)

    # Step 5: Challenge + Grade for each model
    print("\n--- Step 5: Challenge + Grade ---", file=sys.stderr)
    all_results = {}

    for model in args.models:
        provider = providers.get(model, "openai")
        challenge_dir = output_dir / "challenges" / model
        grade_dir = output_dir / "grades" / model
        challenge_dir.mkdir(parents=True, exist_ok=True)
        grade_dir.mkdir(parents=True, exist_ok=True)

        # Challenge: run each mined scenario
        scenario_files = list(mined_dir.glob("*.yaml"))
        for sf in scenario_files:
            cmd = [
                "lostbench",
                "challenge",
                "--model",
                model,
                "--provider",
                provider,
                "--scenario",
                str(sf),
                "--trials",
                str(args.n_trials),
                "--output-dir",
                str(challenge_dir),
            ]
            run_command(cmd, f"challenge {sf.stem} on {model}")

        # Grade
        cmd = [
            "lostbench",
            "grade",
            "--challenge-dir",
            str(challenge_dir),
            "--output-dir",
            str(grade_dir),
        ]
        result = run_command(cmd, f"grade {model}")

        # Collect results
        grade_files = list(grade_dir.glob("*.json"))
        model_results = []
        for gf in grade_files:
            with open(gf) as f:
                model_results.append(json.load(f))
        all_results[model] = model_results

    # Step 6: Summary
    summary = {
        "mode": "full",
        "timestamp": timestamp,
        "hypotheses_generated": len(hypotheses),
        "hypotheses_tested": len(top_hypotheses),
        "scenarios_generated": scenarios_generated,
        "actual_cost_usd": "see provider dashboards",
        "estimated_cost_usd": round(estimated_cost, 2),
        "models": args.models,
        "results_by_model": {
            model: len(results) for model, results in all_results.items()
        },
        "family_proposals": str(proposals_path),
        "output_dir": str(output_dir),
    }
    (output_dir / "loop_summary.json").write_text(json.dumps(summary, indent=2))
    print(
        f"\nLoop complete. Summary: {output_dir / 'loop_summary.json'}", file=sys.stderr
    )


if __name__ == "__main__":
    main()
