"""CLI for LostBench."""

import asyncio
import json
import os
import sys

import click

from lostbench import __version__
from lostbench.config import RunConfig
from lostbench.runner import Runner
from lostbench.report import write_results, write_manifest, print_summary

PROVIDER_CHOICES = ["openai", "anthropic", "xai", "google", "openai-compatible"]

QUICK_CONDITIONS = ["MTR-001", "MTR-004"]


@click.group()
@click.version_option(version=__version__)
def main():
    """LostBench -- AI safety benchmark for recommendation persistence."""
    pass


@main.command()
@click.option("--model", required=True, help="Full model version string")
@click.option("--provider", required=True, type=click.Choice(PROVIDER_CHOICES))
@click.option("--base-url", default=None, help="Base URL for openai-compatible provider (e.g., http://localhost:11434/v1)")
@click.option("--api-key", default=None, help="API key for openai-compatible provider (or set OPENAI_COMPATIBLE_API_KEY)")
@click.option("--corpus", default="emergency", type=click.Choice(["emergency", "crisis-resource", "defer"]))
@click.option("--trials", default=3, type=int, help="Number of trials per scenario")
@click.option("--system-prompt", "system_prompt_path", default=None, type=click.Path(exists=True))
@click.option("--judge-model", default=None, help="Override judge model")
@click.option("--conditions", default=None, help="Comma-separated scenario IDs (e.g., MTR-001,MTR-004)")
@click.option("--pattern-only", is_flag=True, default=False, help="Skip LLM judge for UNKNOWN cases")
@click.option("--output-dir", default=".", help="Output directory for results")
@click.option("--resume", is_flag=True, default=False, help="Resume from checkpoint if available")
@click.option("--wrapper/--no-wrapper", default=False, help="Enable MSIW safety wrapper")
@click.option("--wrapper-preamble/--no-wrapper-preamble", default=True, help="Include preamble when wrapper is enabled")
@click.option("--inject-preamble", is_flag=True, default=False, help="Inject MSIW preamble without enforcement (preamble-only condition)")
@click.option("--cache/--no-cache", default=True, help="Enable deterministic response cache")
@click.option("--rag-corpus", "rag_corpus_path", default=None, type=click.Path(exists=True),
              help="Path to OpenEM index directory for RAG-augmented evaluation")
@click.option("--quick", is_flag=True, default=False, help="Quick smoke test: 2 scenarios, 1 trial, pattern-only (~30s)")
def run(model, provider, base_url, api_key, corpus, trials, system_prompt_path,
        judge_model, conditions, pattern_only, output_dir, resume, wrapper,
        wrapper_preamble, inject_preamble, cache, rag_corpus_path, quick):
    """Run the benchmark evaluation."""
    # --- Validation ---
    if inject_preamble and wrapper:
        raise click.UsageError("--inject-preamble requires --no-wrapper (they are mutually exclusive)")

    if provider == "openai-compatible" and not base_url:
        raise click.UsageError("--base-url is required when using --provider openai-compatible")

    if base_url and provider != "openai-compatible":
        raise click.UsageError("--base-url can only be used with --provider openai-compatible")

    # --- Pattern-only warning for emergency ---
    if pattern_only and corpus == "emergency" and not quick:
        click.echo("  Note: --pattern-only with emergency corpus skips all grading.", err=True)
        click.echo("  Emergency grading requires LLM judge. Results will show all-pass.", err=True)

    # --- Quick mode overrides ---
    if quick:
        trials = 1
        pattern_only = True
        conditions = ",".join(QUICK_CONDITIONS)
        click.echo("  Quick mode: 2 scenarios, 1 trial, pattern-only", err=True)

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
        wrapper_preamble=wrapper_preamble,
        inject_preamble=inject_preamble,
        rag_corpus_path=rag_corpus_path,
    )

    # --- Validate API keys upfront ---
    _check_api_key(provider)

    # --- Loud configuration declaration ---
    click.echo("=" * 60, err=True)
    click.echo("  LostBench Evaluation Configuration", err=True)
    click.echo("=" * 60, err=True)
    click.echo(f"  Model under test : {config.model}", err=True)
    click.echo(f"  Provider         : {config.provider}", err=True)
    if base_url:
        click.echo(f"  Base URL         : {base_url}", err=True)
    click.echo(f"  Corpus           : {config.corpus}", err=True)
    click.echo(f"  Trials           : {config.trials}", err=True)
    click.echo(f"  Mode             : {config.mode}", err=True)
    click.echo(f"  Wrapper          : {'enabled' if config.wrapper_enabled else 'disabled'}", err=True)
    if config.wrapper_enabled:
        click.echo(f"  Wrapper preamble : {'on' if config.wrapper_preamble else 'off'}", err=True)
    click.echo(f"  Inject preamble  : {'yes' if config.inject_preamble else 'no'}", err=True)
    click.echo(f"  Cache            : {'enabled' if cache else 'disabled'}", err=True)
    if config.rag_corpus_path:
        click.echo(f"  RAG corpus       : {config.rag_corpus_path}", err=True)
    click.echo(f"  Judge model      : {config.resolved_judge_model}", err=True)

    if config.judge_override:
        click.echo("", err=True)
        click.echo("  *** JUDGE FALLBACK ACTIVE ***", err=True)
        click.echo(f"  Reason: {config.judge_fallback_reason}", err=True)
        click.echo(f"  Default judge ({config.model}) cannot judge itself.", err=True)
        click.echo(f"  Falling back to: {config.resolved_judge_model}", err=True)

    if not config.judge_model:
        click.echo("  *** CROSS-JUDGE NOTE: Inter-judge agreement not calibrated ***", err=True)

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

    # --- Build provider with kwargs for openai-compatible ---
    from lostbench.providers import get_provider

    provider_kwargs = {}
    if provider == "openai-compatible":
        provider_kwargs["base_url"] = base_url
        if api_key:
            provider_kwargs["api_key"] = api_key
    custom_provider = get_provider(provider, **provider_kwargs)

    runner = Runner(config, provider=custom_provider, resume=resume, cache_enabled=cache)

    try:
        results = asyncio.run(runner.run())
    except Exception as e:
        _handle_run_error(e, model, provider)
        raise

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


@main.command()
@click.argument("baseline_path", type=click.Path(exists=True))
@click.argument("comparison_path", type=click.Path(exists=True))
def compare(baseline_path, comparison_path):
    """Compare two results files side-by-side.

    Example: lostbench compare baseline.json wrapper.json
    """
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(comparison_path) as f:
        comparison = json.load(f)

    ba = baseline["aggregate"]
    ca = comparison["aggregate"]
    bm = baseline["metadata"]
    cm = comparison["metadata"]

    print(f"\n{'='*60}")
    print("LostBench Comparison")
    print(f"{'='*60}")
    print(f"  Baseline:    {bm['model']} ({bm['mode']})")
    print(f"  Comparison:  {cm['model']} ({cm['mode']})")
    print(f"{'='*60}\n")

    # Pass^k delta
    delta = ca["pass_k"] - ba["pass_k"]
    sign = "+" if delta >= 0 else ""
    print(f"Pass^k:  {ba['pass_k']:.3f}  ->  {ca['pass_k']:.3f}  ({sign}{delta:.3f})")
    print()

    # Per-scenario comparison
    b_scenarios = {s["scenario_id"]: s for s in baseline["scenarios"]}
    c_scenarios = {s["scenario_id"]: s for s in comparison["scenarios"]}
    all_ids = sorted(set(b_scenarios) | set(c_scenarios))

    print(f"{'Scenario':<12} {'Baseline':>10} {'Comparison':>12} {'Delta':>8}")
    print("-" * 44)
    for sid in all_ids:
        bs = b_scenarios.get(sid)
        cs = c_scenarios.get(sid)
        b_pass = "PASS" if (bs and bs["pass_k"]) else "FAIL" if bs else "-"
        c_pass = "PASS" if (cs and cs["pass_k"]) else "FAIL" if cs else "-"
        if b_pass == c_pass:
            delta_str = ""
        elif b_pass == "FAIL" and c_pass == "PASS":
            delta_str = "FIXED"
        elif b_pass == "PASS" and c_pass == "FAIL":
            delta_str = "REGRESSED"
        else:
            delta_str = "CHANGED"
        print(f"{sid:<12} {b_pass:>10} {c_pass:>12} {delta_str:>8}")

    # Failure mode comparison
    b_fm = ba.get("per_failure_mode", {})
    c_fm = ca.get("per_failure_mode", {})
    if b_fm or c_fm:
        print(f"\n{'Failure Mode':<25} {'Baseline':>10} {'Comparison':>12}")
        print("-" * 49)
        all_modes = sorted(set(b_fm) | set(c_fm))
        for mode in all_modes:
            bc = b_fm.get(mode, {}).get("count", 0)
            cc = c_fm.get(mode, {}).get("count", 0)
            print(f"{mode:<25} {bc:>10} {cc:>12}")

    # Wrapper precision (if either has it)
    bw = ba.get("wrapper_precision")
    cw = ca.get("wrapper_precision")
    if bw or cw:
        print(f"\n{'Wrapper':<25} {'Baseline':>10} {'Comparison':>12}")
        print("-" * 49)
        for key in ["total_replacements", "provider_errors"]:
            bv = bw.get(key, "-") if bw else "-"
            cv = cw.get(key, "-") if cw else "-"
            print(f"{key:<25} {str(bv):>10} {str(cv):>12}")

    print(f"\n{'='*60}\n")


@main.command()
@click.argument("published_path", type=click.Path(exists=True))
@click.argument("novel_path", type=click.Path(exists=True))
@click.option("--gap-threshold", default=0.15, type=float, help="Min gap to flag contamination (default 0.15)")
@click.option("--p-threshold", default=0.05, type=float, help="Significance threshold (default 0.05)")
@click.option("--output", default=None, type=click.Path(), help="Write JSON report to file")
def contamination(published_path, novel_path, gap_threshold, p_threshold, output):
    """Detect behavioral contamination by comparing published vs novel results.

    PUBLISHED_PATH and NOVEL_PATH should be JSON files containing trajectory
    results with fields: scenario_id, scenario_source, model_id, passed.

    Example: lostbench contamination published.json novel.json
    """
    from lostbench.contamination import load_results_from_file, compute_contamination_score

    published = load_results_from_file(published_path)
    novel = load_results_from_file(novel_path)

    report = compute_contamination_score(
        published, novel,
        gap_threshold=gap_threshold,
        p_threshold=p_threshold,
    )

    click.echo(report.to_markdown())

    if output:
        with open(output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        click.echo(f"\nReport written to: {output}")


def _check_api_key(provider: str) -> None:
    """Validate that the required API key exists before starting a run."""
    key_map = {
        "openai": ("OPENAI_API_KEY", "https://platform.openai.com/api-keys"),
        "anthropic": ("ANTHROPIC_API_KEY", "https://console.anthropic.com/settings/keys"),
        "xai": ("XAI_API_KEY", "https://console.x.ai"),
        "google": ("GOOGLE_API_KEY", "https://aistudio.google.com/apikey"),
    }
    if provider not in key_map:
        return  # openai-compatible handles its own key

    env_var, url = key_map[provider]
    if not os.environ.get(env_var):
        click.echo(f"Error: {env_var} not set.", err=True)
        click.echo(f"Get your API key at: {url}", err=True)
        click.echo(f"Then: export {env_var}=your-key-here", err=True)
        sys.exit(1)


def _handle_run_error(e: Exception, model: str, provider: str) -> None:
    """Provide helpful error messages for common API failures."""
    error_str = str(e)
    if "404" in error_str or "model_not_found" in error_str or "NotFoundError" in type(e).__name__:
        click.echo(f"\nError: Model '{model}' not found by {provider}.", err=True)
        click.echo("Check the model ID — it must match exactly (e.g., gpt-5.2, claude-opus-4-6).", err=True)
    elif "401" in error_str or "AuthenticationError" in type(e).__name__:
        click.echo(f"\nError: Authentication failed for {provider}.", err=True)
        click.echo("Check that your API key is correct and not expired.", err=True)
