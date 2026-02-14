"""CLI for LostBench."""

import asyncio
import json

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
@click.option("--provider", required=True, type=click.Choice(["openai", "anthropic", "xai", "google"]))
@click.option("--corpus", default="emergency", type=click.Choice(["emergency", "crisis-resource"]))
@click.option("--trials", default=3, type=int, help="Number of trials per scenario")
@click.option("--system-prompt", "system_prompt_path", default=None, type=click.Path(exists=True))
@click.option("--judge-model", default=None, help="Override judge model")
@click.option("--conditions", default=None, help="Comma-separated scenario IDs to run")
@click.option("--pattern-only", is_flag=True, default=False, help="Skip LLM judge for UNKNOWN cases")
@click.option("--output-dir", default=".", help="Output directory for results")
@click.option("--resume", is_flag=True, default=False, help="Resume from checkpoint if available")
@click.option("--wrapper/--no-wrapper", default=False, help="Enable MSIW safety wrapper")
@click.option("--cache/--no-cache", default=True, help="Enable deterministic response cache")
def run(model, provider, corpus, trials, system_prompt_path, judge_model,
        conditions, pattern_only, output_dir, resume, wrapper, cache):
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
        wrapper_enabled=wrapper,
    )

    # --- Loud configuration declaration ---
    click.echo("=" * 60, err=True)
    click.echo("  LostBench Evaluation Configuration", err=True)
    click.echo("=" * 60, err=True)
    click.echo(f"  Model under test : {config.model}", err=True)
    click.echo(f"  Provider         : {config.provider}", err=True)
    click.echo(f"  Corpus           : {config.corpus}", err=True)
    click.echo(f"  Trials           : {config.trials}", err=True)
    click.echo(f"  Mode             : {config.mode}", err=True)
    click.echo(f"  Wrapper          : {'enabled' if config.wrapper_enabled else 'disabled'}", err=True)
    click.echo(f"  Cache            : {'enabled' if cache else 'disabled'}", err=True)
    click.echo(f"  Judge model      : {config.resolved_judge_model}", err=True)

    if config.judge_override:
        click.echo("", err=True)
        click.echo("  *** JUDGE FALLBACK ACTIVE ***", err=True)
        click.echo(f"  Reason: {config.judge_fallback_reason}", err=True)
        click.echo(f"  Default judge ({config.model}) cannot judge itself.", err=True)
        click.echo(f"  Falling back to: {config.resolved_judge_model}", err=True)

    if config.judge_model:
        click.echo(f"  (user override: --judge-model {config.judge_model})", err=True)

    click.echo(f"  System prompt    : {config.system_prompt_hash[:16]}...", err=True)
    click.echo(f"  Temperature      : {config.temperature}", err=True)
    click.echo(f"  Seed             : {config.seed}", err=True)
    click.echo(f"  Output dir       : {output_dir}", err=True)
    if resume:
        click.echo("  Resume           : enabled", err=True)
    click.echo("=" * 60, err=True)
    click.echo("", err=True)

    runner = Runner(config, resume=resume, cache_enabled=cache)
    results = asyncio.run(runner.run())
    manifest = runner.build_manifest(results)

    results_path = write_results(results, output_dir)
    manifest_path = write_manifest(manifest, output_dir)

    print_summary(results)
    click.echo(f"Results:  {results_path}")
    click.echo(f"Manifest: {manifest_path}")

    cache_stats = results.get("metadata", {}).get("cache_stats")
    if cache_stats:
        click.echo(
            f"Cache:    {cache_stats['hits']} hits / {cache_stats['total']} calls "
            f"({cache_stats['hit_rate']:.0%} hit rate)",
        )


@main.command()
@click.argument("results_path", type=click.Path(exists=True))
def report(results_path):
    """Print summary from existing results file."""
    with open(results_path) as f:
        results = json.load(f)
    print_summary(results)
