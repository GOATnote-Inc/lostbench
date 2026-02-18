"""Report generation for LostBench."""

import json
from pathlib import Path


def write_results(results: dict, output_dir: str = ".") -> Path:
    """Write results JSON to file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "lostbench_results.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    return path


def write_manifest(manifest: dict, output_dir: str = ".") -> Path:
    """Write manifest JSON to file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "lostbench_manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    return path


def print_summary(results: dict) -> None:
    """Print human-readable summary to stdout."""
    agg = results["aggregate"]
    meta = results["metadata"]

    print(f"\n{'='*60}")
    print(f"LostBench Results \u2014 {meta['corpus']} corpus")
    print(f"{'='*60}")
    print(f"Model:   {meta['model']}")
    print(f"Provider: {meta['provider']}")
    print(f"Judge:   {meta['judge_model']}")
    if meta.get("judge_override"):
        print(f"  (judge override: {meta['judge_fallback_reason']})")
    print(f"Mode:    {meta['mode']}")
    print()
    print(f"Pass^k:  {agg['pass_k']:.3f}")
    print(f"Wilson 95% CI:    [{agg['wilson_ci_95'][0]:.3f}, {agg['wilson_ci_95'][1]:.3f}]")
    print(f"Bootstrap 95% CI: [{agg['bootstrap_ci_95'][0]:.3f}, {agg['bootstrap_ci_95'][1]:.3f}]")
    print(f"Scenarios: {agg['total_scenarios']}, Trials: {agg['total_trials']}")
    print()

    if "per_failure_mode" in agg:
        print("Failure modes:")
        for mode, stats in agg["per_failure_mode"].items():
            if isinstance(stats, dict) and "count" in stats:
                print(f"  {mode}: {stats['count']} ({stats['rate']:.1%})")

    if "per_pressure_type" in agg:
        print("\nPressure type failure rates:")
        for ptype, stats in agg["per_pressure_type"].items():
            print(f"  {ptype}: {stats['failure_rate']:.1%} (n={stats['n']})")

    if "wrapper_precision" in agg:
        wp = agg["wrapper_precision"]
        print("\nWrapper replacements:")
        print(f"  Total:           {wp['total_replacements']}")
        if wp.get("provider_errors", 0) > 0:
            print(f"  Provider errors: {wp['provider_errors']}")

    print(f"\n{'='*60}\n")
