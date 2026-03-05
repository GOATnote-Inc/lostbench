#!/usr/bin/env python3
"""Suite Membership Auto-Evolution.

Scans campaign results → proposes promotions/retirements for
results/suite_membership.yaml.

Promotion: scenario broke >= 2 frontier models → regression suite.
Retirement flag: scenario passed 5 consecutive campaigns → flag for hardening.

Usage:
    python3 scripts/evolve_suite.py                    # dry-run (default)
    python3 scripts/evolve_suite.py --apply             # write changes
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO_ROOT / "results" / "suite_membership.yaml"
INDEX_PATH = REPO_ROOT / "results" / "index.yaml"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _collect_scenario_results(index: dict) -> dict[str, dict]:
    """Aggregate per-scenario results across campaigns.

    Returns {scenario_id: {models_broken: set, campaigns_passed_all: int, last_tested: str}}
    """
    # We need per-scenario data from CEIS result files, but index.yaml
    # only has aggregate data. Use scenario_tracking from suite_membership
    # as a starting point, then update from index.
    tracking: dict[str, dict] = {}

    experiments = index.get("experiments", [])
    for exp in experiments:
        exp_date = exp.get("date", "")
        model = exp.get("model", "")
        pass_k = exp.get("pass_k")

        # We track at the experiment level since we don't have
        # per-scenario data from index.yaml alone.
        # The scenario-level tracking is populated by the campaign engine.
        if pass_k is not None and pass_k < 1.0:
            # This model had failures — but we don't know which scenarios
            # Mark all scenarios from this corpus as potentially broken
            corpus = exp.get("corpus", "")
            if corpus:
                key = f"{corpus}:{model}"
                tracking.setdefault(
                    key,
                    {
                        "models_broken": set(),
                        "last_tested": exp_date,
                    },
                )
                tracking[key]["models_broken"].add(model)
                if exp_date > tracking[key]["last_tested"]:
                    tracking[key]["last_tested"] = exp_date

    return tracking


def evolve_suite(
    suite: dict,
    index: dict,
) -> tuple[list[dict], list[dict]]:
    """Propose promotions and retirement flags.

    Returns (promotions, retirements).
    """
    promotions = []
    retirements = []
    tracking = suite.get("scenario_tracking", {})

    for scenario_id, data in tracking.items():
        models_broken = data.get("models_broken", [])
        consecutive_pass = data.get("consecutive_all_pass", 0)
        last_tested = data.get("last_tested", "")

        # Promotion: broke >= 2 frontier models
        if isinstance(models_broken, list) and len(models_broken) >= 2:
            # Check if already in regression suite
            in_regression = False
            for corpus_key in (
                "emergency",
                "adversarial",
                "code-agent",
                "tool-use",
                "multimodal",
                "integrated",
                "seeds",
            ):
                corpus_data = suite.get(corpus_key, {})
                if scenario_id in corpus_data.get("regression", []):
                    in_regression = True
                    break

            if not in_regression:
                promotions.append(
                    {
                        "scenario_id": scenario_id,
                        "action": "promote",
                        "reason": f"Broke {len(models_broken)} models: {', '.join(models_broken)}",
                        "last_tested": last_tested,
                    }
                )

        # Retirement flag: passed 5 consecutive campaigns
        if consecutive_pass >= 5:
            retirements.append(
                {
                    "scenario_id": scenario_id,
                    "action": "flag_retirement",
                    "reason": f"Passed {consecutive_pass} consecutive campaigns",
                    "last_tested": last_tested,
                }
            )

    return promotions, retirements


def apply_promotions(suite: dict, promotions: list[dict]) -> dict:
    """Apply promotions to suite membership."""
    for promo in promotions:
        sid = promo["scenario_id"]
        # Determine corpus from scenario ID prefix
        prefix = sid.split("-")[0] if "-" in sid else ""
        corpus_map = {
            "MTR": "emergency",
            "CRS": "crisis-resource",
            "DEF": "defer",
            "ADV": "adversarial",
            "CAM": "code-agent",
            "TUE": "tool-use",
            "MMV": "multimodal",
            "PRI": "integrated",
            "SEED": "seeds",
            "GEN": "seeds",
            "CYC": "seeds",
        }
        corpus = corpus_map.get(prefix, "emergency")

        if corpus not in suite:
            suite[corpus] = {"regression": [], "capability": []}

        corpus_data = suite[corpus]
        if sid not in corpus_data.get("regression", []):
            corpus_data.setdefault("regression", []).append(sid)
        if sid in corpus_data.get("capability", []):
            corpus_data["capability"].remove(sid)

    suite["last_updated"] = date.today().isoformat()
    return suite


def render_report(promotions: list[dict], retirements: list[dict]) -> str:
    """Render evolution report."""
    lines = [
        "# Suite Evolution Report",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
    ]

    if promotions:
        lines.append("## Promotions (capability → regression)")
        lines.append("")
        lines.append("[PROPOSED CHANGES]")
        lines.append("")
        for p in promotions:
            lines.append(
                f"- **{p['scenario_id']}**: {p['reason']} (last tested: {p['last_tested']})"
            )
        lines.append("")
        lines.append("[END PROPOSED CHANGES]")
        lines.append("")

    if retirements:
        lines.append("## Retirement Flags")
        lines.append("")
        lines.append("[PROPOSED CHANGES]")
        lines.append("")
        for r in retirements:
            lines.append(
                f"- **{r['scenario_id']}**: {r['reason']} (last tested: {r['last_tested']})"
            )
        lines.append("")
        lines.append("Consider hardening these scenarios or adding variants.")
        lines.append("")
        lines.append("[END PROPOSED CHANGES]")
        lines.append("")

    if not promotions and not retirements:
        lines.append("No promotions or retirements to propose.")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Suite membership auto-evolution from campaign results"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply promotions (default: dry-run report only)",
    )
    parser.add_argument(
        "--suite",
        default=str(SUITE_PATH),
        help="Path to suite_membership.yaml",
    )
    args = parser.parse_args()

    suite_path = Path(args.suite)
    suite = load_yaml(suite_path)
    index = load_yaml(INDEX_PATH)

    promotions, retirements = evolve_suite(suite, index)

    print(render_report(promotions, retirements))

    if promotions:
        print(f"{len(promotions)} promotions proposed", file=sys.stderr)
    if retirements:
        print(f"{len(retirements)} retirements flagged", file=sys.stderr)

    if args.apply and promotions:
        suite = apply_promotions(suite, promotions)
        with open(suite_path, "w") as f:
            yaml.dump(suite, f, default_flow_style=False, sort_keys=False)
        print(f"Suite membership updated: {suite_path}", file=sys.stderr)
    elif args.apply:
        print("No promotions to apply", file=sys.stderr)


if __name__ == "__main__":
    main()
