#!/usr/bin/env python3
"""Campaign Runner — Orchestrates multi-config campaign execution.

Usage:
    python scripts/run_campaign.py \
        --template configs/campaign_templates/new_model_intake.yaml \
        --model gpt-5.2 \
        --provider openai \
        --output-dir results/campaign-2026-02-25/

    # Dry run (validate config, no API calls):
    python scripts/run_campaign.py \
        --template configs/campaign_templates/regression_fast.yaml \
        --model gpt-5.2 \
        --provider openai \
        --dry-run
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_template(path: Path) -> dict:
    """Load a campaign template YAML."""
    with open(path) as f:
        return yaml.safe_load(f)


def apply_overrides(template: dict, model: str, provider: str, output_dir: str) -> dict:
    """Apply CLI overrides to a campaign template."""
    config = dict(template)
    config["model"] = model
    config["provider"] = provider
    config["output_dir"] = output_dir
    return config


def write_runtime_config(config: dict, output_path: Path) -> None:
    """Write a runtime CEIS config YAML."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def run_ceis(config_path: Path, cache: bool = True, resume: bool = False) -> int:
    """Run lostbench ceis run with the given config. Returns exit code."""
    lostbench_bin = shutil.which("lostbench")
    if lostbench_bin is None:
        print(
            "Error: 'lostbench' CLI not found on PATH. Install with: pip install -e .",
            file=sys.stderr,
        )
        return 1
    cmd = [lostbench_bin, "ceis", "run", "--config", str(config_path)]
    if cache:
        cmd.append("--cache")
    else:
        cmd.append("--no-cache")
    if resume:
        cmd.append("--resume")

    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def generate_campaign_summary(output_dir: Path) -> dict:
    """Aggregate results from all CEIS runs in the campaign directory."""
    summary = {
        "campaign_dir": str(output_dir),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runs": [],
    }

    for ceis_path in sorted(output_dir.rglob("ceis_results.json")):
        try:
            with open(ceis_path) as f:
                data = json.load(f)
            meta = data.get("meta", {})
            agg = data.get("aggregate", {})
            summary["runs"].append(
                {
                    "path": str(ceis_path.relative_to(output_dir)),
                    "model": meta.get("model_id", ""),
                    "corpus": meta.get("corpus_version", ""),
                    "ers": agg.get("ERS"),
                    "pass_k": agg.get("pass_k"),
                    "class_a": agg.get("total_classA_failures", 0),
                    "meets_threshold": agg.get("meets_threshold"),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Campaign Runner — orchestrate multi-config CEIS campaigns"
    )
    parser.add_argument(
        "--template",
        required=True,
        type=Path,
        help="Path to campaign template YAML",
    )
    parser.add_argument("--model", required=True, help="Model under test")
    parser.add_argument("--provider", required=True, help="API provider")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: results/campaign-{date}/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config without running evaluations",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable response cache",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint if available",
    )

    args = parser.parse_args()

    # Load template
    template = load_template(args.template)
    print(f"Template: {args.template}")
    print(f"Model: {args.model}")
    print(f"Provider: {args.provider}")

    # Output directory
    if args.output_dir:
        output_dir = args.output_dir
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        output_dir = Path(f"results/campaign-{date_str}")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {output_dir}")

    # Apply overrides
    config = apply_overrides(template, args.model, args.provider, str(output_dir))

    # Write runtime config
    runtime_config_path = output_dir / "campaign_config.yaml"
    write_runtime_config(config, runtime_config_path)
    print(f"Config: {runtime_config_path}")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(f"Would run: lostbench ceis run --config {runtime_config_path}")
        print(f"Model: {config['model']}")
        print(f"Provider: {config['provider']}")
        print(f"Corpus: {config.get('corpus', 'emergency')}")
        print(f"Trials: {config.get('n_trials', 3)}")
        print(f"Temperature: {config.get('temperature', 0.0)}")
        print(f"Seed: {config.get('seed', 42)}")
        print("Config validated successfully.")
        return

    # Run CEIS evaluation
    print("\nRunning CEIS evaluation...")
    exit_code = run_ceis(
        runtime_config_path,
        cache=not args.no_cache,
        resume=args.resume,
    )

    if exit_code != 0:
        print(f"CEIS run failed with exit code {exit_code}", file=sys.stderr)
        sys.exit(exit_code)

    # Generate campaign summary
    summary = generate_campaign_summary(output_dir)
    summary_path = output_dir / "campaign_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nCampaign summary: {summary_path}")

    # Print results
    for run in summary["runs"]:
        status = "PASS" if run.get("meets_threshold") else "FAIL"
        print(f"  {run['corpus']}: ERS={run['ers']} Pass^k={run['pass_k']} [{status}]")


if __name__ == "__main__":
    main()
