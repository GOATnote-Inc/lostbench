"""Report generation for LostBench."""

import csv
import io
import json
from pathlib import Path

import click


def write_results(results: dict, output_dir: str = ".") -> Path:
    """Write results JSON to file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "lostbench_results.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    return path


def write_manifest(manifest: dict, output_dir: str = ".") -> Path:
    """Write manifest JSON to file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "lostbench_manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    return path


def _require_keys(results: dict) -> tuple[dict, dict]:
    """Extract aggregate and metadata, raising on missing keys."""
    try:
        return results["aggregate"], results["metadata"]
    except KeyError as e:
        raise ValueError(f"Results missing required key: {e}") from e


def print_summary(results: dict) -> None:
    """Print human-readable summary to stdout."""
    agg, meta = _require_keys(results)

    click.echo(f"\n{'=' * 60}")
    click.echo(f"LostBench Results \u2014 {meta['corpus']} corpus")
    click.echo(f"{'=' * 60}")
    click.echo(f"Model:   {meta['model']}")
    click.echo(f"Provider: {meta['provider']}")
    click.echo(f"Judge:   {meta['judge_model']}")
    if meta.get("judge_override"):
        click.echo(f"  (judge override: {meta['judge_fallback_reason']})")
    click.echo(f"Mode:    {meta['mode']}")
    click.echo()
    click.echo(f"Pass^k:  {agg['pass_k']:.3f}")
    click.echo(
        f"Wilson 95% CI:    [{agg['wilson_ci_95'][0]:.3f}, {agg['wilson_ci_95'][1]:.3f}]"
    )
    click.echo(
        f"Bootstrap 95% CI: [{agg['bootstrap_ci_95'][0]:.3f}, {agg['bootstrap_ci_95'][1]:.3f}]"
    )
    click.echo(f"Scenarios: {agg['total_scenarios']}, Trials: {agg['total_trials']}")
    click.echo()

    if "per_failure_mode" in agg:
        click.echo("Failure modes:")
        for mode, stats in agg["per_failure_mode"].items():
            if isinstance(stats, dict) and "count" in stats:
                click.echo(f"  {mode}: {stats['count']} ({stats['rate']:.1%})")

    if "per_pressure_type" in agg:
        click.echo("\nPressure type failure rates:")
        for ptype, stats in agg["per_pressure_type"].items():
            click.echo(f"  {ptype}: {stats['failure_rate']:.1%} (n={stats['n']})")

    if "wrapper_precision" in agg:
        wp = agg["wrapper_precision"]
        click.echo("\nWrapper replacements:")
        click.echo(f"  Total:           {wp['total_replacements']}")
        if wp.get("provider_errors", 0) > 0:
            click.echo(f"  Provider errors: {wp['provider_errors']}")

    click.echo(f"\n{'=' * 60}\n")


def format_markdown(results: dict) -> str:
    """Format results as Markdown table."""
    agg, meta = _require_keys(results)
    lines = [
        f"# LostBench Results — {meta['corpus']} corpus\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Model | {meta['model']} |",
        f"| Provider | {meta['provider']} |",
        f"| Judge | {meta['judge_model']} |",
        f"| Mode | {meta['mode']} |",
        f"| Pass^k | {agg['pass_k']:.3f} |",
        f"| Wilson 95% CI | [{agg['wilson_ci_95'][0]:.3f}, {agg['wilson_ci_95'][1]:.3f}] |",
        f"| Bootstrap 95% CI | [{agg['bootstrap_ci_95'][0]:.3f}, {agg['bootstrap_ci_95'][1]:.3f}] |",
        f"| Scenarios | {agg['total_scenarios']} |",
        f"| Trials | {agg['total_trials']} |",
    ]

    if "per_failure_mode" in agg and agg["per_failure_mode"]:
        lines.append("")
        lines.append("## Failure Modes\n")
        lines.append("| Mode | Count | Rate |")
        lines.append("|------|-------|------|")
        for mode, stats in agg["per_failure_mode"].items():
            if isinstance(stats, dict) and "count" in stats:
                lines.append(f"| {mode} | {stats['count']} | {stats['rate']:.1%} |")

    if "per_pressure_type" in agg and agg["per_pressure_type"]:
        lines.append("")
        lines.append("## Pressure Type Failure Rates\n")
        lines.append("| Type | Failure Rate | N |")
        lines.append("|------|-------------|---|")
        for ptype, stats in agg["per_pressure_type"].items():
            lines.append(f"| {ptype} | {stats['failure_rate']:.1%} | {stats['n']} |")

    return "\n".join(lines) + "\n"


def format_csv(results: dict) -> str:
    """Format per-scenario results as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["scenario_id", "pass_k", "trials_run", "trials_passed"])
    for scenario in results.get("scenarios", []):
        writer.writerow(
            [
                scenario["scenario_id"],
                scenario["pass_k"],
                scenario["trials_run"],
                scenario["trials_passed"],
            ]
        )
    return output.getvalue()
