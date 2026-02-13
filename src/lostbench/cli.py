"""CLI for LostBench."""

import asyncio
import json
import sys

import click

from lostbench import __version__
from lostbench.config import RunConfig
from lostbench.runner import Runner
from lostbench.report import write_results, write_manifest, print_summary


@click.group()
@click.version_option(version=__version__)
def main():
    """LostBench -- AI safety benchmark for recommendation persistence."""
    pass


@main.command()
@click.option("--model", required=True, help="Full model version string")
@click.option("--provider", required=True, type=click.Choice(["openai", "anthropic", "xai"]))
@click.option("--corpus", default="emergency", type=click.Choice(["emergency", "crisis-resource"]))
@click.option("--trials", default=3, type=int, help="Number of trials per scenario")
@click.option("--system-prompt", "system_prompt_path", default=None, type=click.Path(exists=True))
@click.option("--judge-model", default=None, help="Override judge model")
@click.option("--conditions", default=None, help="Comma-separated scenario IDs to run")
@click.option("--pattern-only", is_flag=True, default=False, help="Skip LLM judge for UNKNOWN cases")
@click.option("--output-dir", default=".", help="Output directory for results")
def run(model, provider, corpus, trials, system_prompt_path, judge_model,
        conditions, pattern_only, output_dir):
    """Run the benchmark evaluation."""
    conditions_list = (
        [c.strip() for c in conditions.split(",")]
        if conditions else None
    )

    config = RunConfig(
        model=model,
        provider=provider,
        corpus=corpus,
        trials=trials,
        system_prompt_path=system_prompt_path,
        judge_model=judge_model,
        conditions=conditions_list,
        pattern_only=pattern_only,
        output_dir=output_dir,
    )

    runner = Runner(config)
    results = asyncio.run(runner.run())
    manifest = runner.build_manifest(results)

    results_path = write_results(results, output_dir)
    manifest_path = write_manifest(manifest, output_dir)

    print_summary(results)
    click.echo(f"Results:  {results_path}")
    click.echo(f"Manifest: {manifest_path}")


@main.command()
@click.argument("results_path", type=click.Path(exists=True))
def report(results_path):
    """Print summary from existing results file."""
    with open(results_path) as f:
        results = json.load(f)
    print_summary(results)
