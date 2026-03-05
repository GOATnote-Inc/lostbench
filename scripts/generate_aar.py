#!/usr/bin/env python3
"""After-Action Review (AAR) Generator.

Auto-generates AAR from campaign results + mining analysis,
following the format established in docs/aars/AAR-MSTS-CROSSVENDOR.md.

Sections: Campaign ID, Date Range, Objective, Setup, Key Findings,
Root Causes (mapped to exploit families), Corrective Actions,
Surprises, Open Questions, Metrics Delta, Grading Layer Analysis.

Usage:
    python3 scripts/generate_aar.py --campaign-id CAMPAIGN-2026-03-05 --results-dir results/ceis-n5/
    python3 scripts/generate_aar.py --campaign-id CAMPAIGN-2026-03-05 --results-dir results/ceis-n5/ --prior-dir results/ceis-n3/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = REPO_ROOT / "results" / "analysis"
FAMILIES_PATH = REPO_ROOT / "configs" / "exploit_families.yaml"
AARS_DIR = REPO_ROOT / "docs" / "aars"


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def load_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def find_ceis_results(results_dir: Path) -> list[dict]:
    """Find and load all CEIS result JSONs in a directory."""
    results = []
    for p in sorted(results_dir.rglob("*.json")):
        try:
            data = json.loads(p.read_text())
            if "aggregate" in data or "conditions" in data:
                results.append(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return results


def _class_a_conditions(results: list[dict]) -> list[dict]:
    """Extract all conditions with Class A failures."""
    class_a = []
    for r in results:
        for c in r.get("conditions", []):
            if c.get("classA", 0) > 0:
                class_a.append(
                    {
                        "condition": c.get("condition", "unknown"),
                        "class_a": c.get("classA", 0),
                        "eps_wilson_lower": c.get("eps_wilson_lower", 0),
                        "model": r.get("meta", {}).get("model_id", "unknown"),
                    }
                )
    return class_a


def _map_to_families(
    conditions: list[dict], registry: dict | None
) -> dict[str, list[str]]:
    """Map Class A conditions to exploit families."""
    if not registry:
        return {}
    family_map: dict[str, list[str]] = {}
    for fam in registry.get("families", []):
        fam_id = fam["family_id"]
        name = fam.get("name", "")
        for c in conditions:
            cond = c["condition"]
            # Check if condition is targeted by this family's vector
            if fam.get("vector") in ("adversarial", "integrated", "emergency"):
                family_map.setdefault(f"{fam_id} ({name})", []).append(cond)
    return family_map


def generate_aar(
    campaign_id: str,
    results: list[dict],
    prior_results: list[dict] | None = None,
    mining: dict | None = None,
    registry: dict | None = None,
) -> str:
    """Generate AAR markdown from campaign results."""
    today = date.today().isoformat()
    lines = [
        f"# After-Action Review: {campaign_id}",
        "",
        f"**Generated:** {today}",
        "**Status:** AUTO-GENERATED — requires campaign-lead review",
        "",
        "---",
        "",
    ]

    # Setup
    models = set()
    total_scenarios = 0
    total_trials = 0
    for r in results:
        meta = r.get("meta", {})
        models.add(meta.get("model_id", "unknown"))
        total_scenarios += meta.get("n_scenarios", 0)
        total_trials += meta.get("n_trials", 0)

    lines.extend(
        [
            "## Setup",
            "",
            f"- **Campaign:** {campaign_id}",
            f"- **Date:** {today}",
            f"- **Models:** {', '.join(sorted(models))}",
            f"- **Total scenarios:** {total_scenarios}",
            f"- **Trials per scenario:** {total_trials}",
            "- **Determinism:** seed=42, temperature=0.0",
            "",
        ]
    )

    # Key Findings
    lines.extend(["## Key Findings", ""])

    class_a = _class_a_conditions(results)
    if class_a:
        lines.append(f"### Class A Failures ({len(class_a)} conditions)")
        lines.append("")
        lines.append("| Condition | Model | Class A Count | EPS Wilson Lower |")
        lines.append("|-----------|-------|---------------|------------------|")
        for c in sorted(class_a, key=lambda x: -x["class_a"]):
            lines.append(
                f"| {c['condition']} | {c['model']} | {c['class_a']} | {c['eps_wilson_lower']:.3f} |"
            )
        lines.append("")
    else:
        lines.append("No Class A failures detected.")
        lines.append("")

    # Aggregate metrics
    for r in results:
        agg = r.get("aggregate", {})
        meta = r.get("meta", {})
        model = meta.get("model_id", "unknown")
        lines.extend(
            [
                f"### {model}",
                "",
                f"- ERS: {agg.get('ERS', 'N/A')}",
                f"- Pass^k: {agg.get('pass_k', 'N/A')}",
                f"- Meets threshold: {'Yes' if agg.get('meets_threshold') else 'No'}",
                f"- Class A total: {agg.get('total_classA_failures', 0)}",
                f"- Class D total: {agg.get('total_classD_failures', 0)}",
                "",
            ]
        )

    # Grading Layer Analysis
    lines.extend(
        [
            "## Grading Layer Analysis",
            "",
            "**Note:** Python pattern matching (Layer 0) has a documented 30-97% "
            "false negative rate. LLM judge (Layer 2) is the authoritative grading "
            "source. High Layer 0 resolution percentages should be treated with "
            "caution — they may indicate missed failures.",
            "",
        ]
    )

    for r in results:
        gm = r.get("grading_metadata", {})
        meta = r.get("meta", {})
        if gm:
            model = meta.get("model_id", "unknown")
            l0_pct = gm.get("layer_0_pct", 0)
            l2_pct = gm.get("layer_2_pct", 0)
            lines.append(f"### {model}")
            lines.append("")
            lines.append(
                f"- Layer 0 resolved: {gm.get('layer_0_resolved', 0)} ({l0_pct:.1f}%)"
            )
            lines.append(
                f"- Layer 2 resolved: {gm.get('layer_2_resolved', 0)} ({l2_pct:.1f}%)"
            )
            if l0_pct > 50:
                lines.append(
                    f"- **WARNING:** Layer 0 resolved {l0_pct:.0f}% of grades — "
                    f"verify no false negatives from pattern matching"
                )
            lines.append("")

    # Root Causes (mapped to exploit families)
    if registry and class_a:
        family_map = _map_to_families(class_a, registry)
        if family_map:
            lines.extend(["## Root Causes (Exploit Family Mapping)", ""])
            for fam_label, conditions in family_map.items():
                unique = sorted(set(conditions))
                lines.append(f"- **{fam_label}:** {', '.join(unique)}")
            lines.append("")

    # Metrics Delta (if prior results available)
    if prior_results:
        lines.extend(["## Metrics Delta (vs Prior)", ""])
        lines.append(
            "| Model | Prior ERS | Current ERS | Delta | Prior Pass^k | Current Pass^k | Delta |"
        )
        lines.append(
            "|-------|-----------|-------------|-------|-------------|----------------|-------|"
        )

        for r in results:
            meta = r.get("meta", {})
            model = meta.get("model_id", "")
            agg = r.get("aggregate", {})
            current_ers = agg.get("ERS")
            current_pk = agg.get("pass_k")

            # Find matching prior
            for pr in prior_results:
                pr_meta = pr.get("meta", {})
                if pr_meta.get("model_id") == model:
                    pr_agg = pr.get("aggregate", {})
                    prior_ers = pr_agg.get("ERS")
                    prior_pk = pr_agg.get("pass_k")

                    ers_delta = ""
                    if current_ers is not None and prior_ers is not None:
                        ers_delta = f"{current_ers - prior_ers:+.1f}"
                    pk_delta = ""
                    if current_pk is not None and prior_pk is not None:
                        pk_delta = f"{current_pk - prior_pk:+.3f}"

                    lines.append(
                        f"| {model} | {prior_ers} | {current_ers} | {ers_delta} | "
                        f"{prior_pk} | {current_pk} | {pk_delta} |"
                    )
                    break
        lines.append("")

    # Corrective Actions
    lines.extend(
        [
            "## Corrective Actions",
            "",
            "- [ ] Review all Class A conditions for risk debt entries",
            "- [ ] Update exploit family persistence status",
            "- [ ] Run targeted hunt on highest-severity failures",
            "- [ ] Update suite membership if scenarios broke multiple models",
            "",
        ]
    )

    # Open Questions
    lines.extend(
        [
            "## Open Questions",
            "",
            "- Are Class A failures reproducible across provider API versions?",
            "- Do mitigation interventions (preamble/wrapper) address root causes?",
            "- Are there novel failure patterns not captured by existing exploit families?",
            "",
        ]
    )

    lines.extend(
        [
            "---",
            "",
            f"*Auto-generated by `scripts/generate_aar.py` on {today}. "
            f"Requires campaign-lead review before finalization.*",
        ]
    )

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Generate After-Action Review from campaign results"
    )
    parser.add_argument(
        "--campaign-id",
        required=True,
        help="Campaign identifier (e.g., CAMPAIGN-2026-03-05)",
    )
    parser.add_argument(
        "--results-dir",
        required=True,
        help="Directory containing CEIS result JSONs",
    )
    parser.add_argument(
        "--prior-dir",
        default=None,
        help="Optional prior results directory for delta comparison",
    )
    parser.add_argument(
        "--output-dir",
        default=str(AARS_DIR),
        help="Output directory for AAR (default: docs/aars/)",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = find_ceis_results(results_dir)
    if not results:
        print(f"No CEIS results found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    prior_results = None
    if args.prior_dir:
        prior_results = find_ceis_results(Path(args.prior_dir))

    registry = load_yaml(FAMILIES_PATH)

    aar = generate_aar(
        campaign_id=args.campaign_id,
        results=results,
        prior_results=prior_results,
        registry=registry,
    )

    output_path = output_dir / f"AAR-{args.campaign_id}.md"
    output_path.write_text(aar)
    print(f"AAR written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
