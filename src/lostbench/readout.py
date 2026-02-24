"""Executive Readout Generator.

Generates templated readout documents from CEIS results + exploit family data.
Three templates: executive (1-page), partner (external), internal (full detail).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _load_ceis_results(path: Path | str) -> dict:
    """Load a CEIS results JSON file."""
    with open(path) as f:
        return json.load(f)


def _format_conditions_table(conditions: list[dict], max_rows: int = 10) -> str:
    """Format a markdown table of conditions below threshold."""
    lines = ["| Condition | EPS | Class A | Class B | Class D | Passed |"]
    lines.append("|-----------|-----|---------|---------|---------|--------|")
    failed = [c for c in conditions if not c.get("passed", False)]
    for c in failed[:max_rows]:
        passed = "PASS" if c.get("passed") else "FAIL"
        lines.append(
            f"| {c.get('condition', '')} | {c.get('eps_wilson_lower', 0):.2f} | "
            f"{c.get('classA', 0)} | {c.get('classB', 0)} | {c.get('classD', 0)} | {passed} |"
        )
    if len(failed) > max_rows:
        lines.append(f"| ... and {len(failed) - max_rows} more | | | | | |")
    return "\n".join(lines)


def generate_readout(
    ceis_results: dict,
    family_registry: dict | None = None,
    prior_results: dict | None = None,
    template: str = "executive",
) -> str:
    """Generate formatted readout from CEIS results.

    Args:
        ceis_results: Parsed CEIS JSON artifact
        family_registry: Parsed exploit_families.yaml (optional)
        prior_results: Prior CEIS results for regression comparison (optional)
        template: "executive" | "partner" | "internal"
    """
    if template == "executive":
        return _executive_readout(ceis_results, family_registry, prior_results)
    elif template == "partner":
        return _partner_readout(ceis_results, family_registry)
    elif template == "internal":
        return _internal_readout(ceis_results, family_registry, prior_results)
    else:
        raise ValueError(f"Unknown template: {template}. Use executive, partner, or internal.")


def _executive_readout(
    results: dict,
    registry: dict | None,
    prior: dict | None,
) -> str:
    """Executive readout -- 1 page max."""
    meta = results.get("meta", {})
    agg = results.get("aggregate", {})
    conditions = results.get("conditions", [])
    regression = results.get("regression")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "# Executive Risk Readout",
        "",
        f"**Date:** {date_str}",
        f"**Model:** {meta.get('model_id', 'unknown')}",
        f"**Corpus:** {meta.get('corpus_version', 'unknown')}",
        f"**Run:** {meta.get('run_id', 'unknown')}",
        "",
        "## Risk Snapshot",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| ERS | {agg.get('ERS', 'N/A')} / 100 (CI: {agg.get('ERS_bootstrap_ci', [0, 0])}) |",
        f"| Pass^k | {agg.get('pass_k', 'N/A')} |",
        f"| Meets Threshold | {'Yes' if agg.get('meets_threshold') else 'No'} |",
        f"| Class A Failures | {agg.get('total_classA_failures', 0)} |",
        f"| Class D Failures | {agg.get('total_classD_failures', 0)} |",
        f"| Scenarios | {meta.get('n_scenarios', 0)} |",
        f"| Trials | {meta.get('n_trials', 0)} |",
        "",
    ]

    # Highest-severity findings
    class_a_conditions = [c for c in conditions if c.get("classA", 0) > 0]
    if class_a_conditions:
        lines.append("## Highest-Severity Findings")
        lines.append("")
        lines.append(_format_conditions_table(class_a_conditions, max_rows=5))
        lines.append("")

    # Mitigation status from family registry
    if registry:
        lines.append("## Exploit Family Status")
        lines.append("")
        lines.append("| Family | Status | Baseline | Mitigated | Best Mitigation |")
        lines.append("|--------|--------|----------|-----------|-----------------|")
        model_id = meta.get("model_id", "")
        for fam in registry.get("families", []):
            for p in fam.get("persistence", []):
                if p["model"] == model_id:
                    status_str = p.get("status", "unknown")
                    lines.append(
                        f"| {fam['family_id']} ({fam['name']}) | {status_str} | "
                        f"{p.get('baseline_pass_k', 'N/A')} | {p.get('mitigated_pass_k', 'N/A')} | "
                        f"{p.get('best_mitigation', 'N/A')} |"
                    )
        lines.append("")

    # Regression
    if regression:
        reg_detected = regression.get("regression_detected", False)
        lines.append("## Regression")
        lines.append("")
        lines.append(f"- Prior model: {regression.get('prior_model_id', 'unknown')}")
        lines.append(f"- ERS delta: {regression.get('ers_delta', 0)}")
        lines.append(f"- Regression detected: {'Yes' if reg_detected else 'No'}")
        if regression.get("new_classA_conditions"):
            lines.append(f"- New Class A: {', '.join(regression['new_classA_conditions'])}")
        lines.append("")

    # Residual risk
    lines.append("## Residual Risk")
    lines.append("")
    if not agg.get("meets_threshold"):
        lines.append("- Model does not meet CEIS deployment threshold")
    if agg.get("total_classA_failures", 0) > 0:
        lines.append(f"- {agg['total_classA_failures']} Class A failures across {len(class_a_conditions)} conditions")
    if agg.get("total_classD_failures", 0) > 0:
        lines.append(f"- {agg['total_classD_failures']} citation hallucinations (Class D)")
    lines.append("")

    # Reproduction
    lines.append("## Reproduction")
    lines.append("")
    lines.append("```bash")
    lines.append("lostbench ceis run --config <config.yaml>")
    lines.append(f"# seed={meta.get('seed', 42)}, temperature={meta.get('temperature', 0.0)}, n_trials={meta.get('n_trials', 3)}")
    lines.append("```")

    return "\n".join(lines) + "\n"


def _partner_readout(results: dict, registry: dict | None) -> str:
    """Partner readout -- external-facing, sanitized."""
    meta = results.get("meta", {})
    agg = results.get("aggregate", {})
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "# Safety Evaluation Summary",
        "",
        f"**Date:** {date_str}",
        f"**Model:** {meta.get('model_id', 'unknown')}",
        "",
        "## Risk Posture",
        "",
        f"Escalation Risk Score: **{agg.get('ERS', 'N/A')} / 100**",
        "",
        f"The model was evaluated across {meta.get('n_scenarios', 0)} clinical emergency scenarios "
        f"with {meta.get('n_trials', 0)} independent trials per scenario.",
        "",
    ]

    threshold_met = agg.get("meets_threshold", False)
    if threshold_met:
        lines.append("The model **meets** the minimum safety persistence threshold for the tested scenarios.")
    else:
        lines.append("The model **does not meet** the minimum safety persistence threshold.")
        if agg.get("threshold_failures"):
            lines.append("")
            lines.append("Threshold failures:")
            for f in agg["threshold_failures"]:
                lines.append(f"- {f}")

    lines.extend([
        "",
        "## Methodology",
        "",
        "Evaluation uses a 3-layer grading pipeline: deterministic pattern matching followed by "
        "cross-vendor LLM judge assessment. Confidence intervals are computed using Wilson score "
        "intervals and scenario-level bootstrap resampling (10,000 iterations).",
        "",
        "All evaluations use fixed deterministic settings (temperature=0.0, seed=42) for reproducibility.",
    ])

    return "\n".join(lines) + "\n"


def _internal_readout(
    results: dict,
    registry: dict | None,
    prior: dict | None,
) -> str:
    """Internal readout -- full detail."""
    # Start with executive content
    readout = _executive_readout(results, registry, prior)

    conditions = results.get("conditions", [])

    lines = [readout.rstrip()]

    # Full conditions table
    lines.append("\n## All Conditions (Internal Detail)")
    lines.append("")
    lines.append("| Condition | Severity | EPS Point | EPS Lower | Class A | Class B | Class C | Class D | CRS | Passed |")
    lines.append("|-----------|----------|-----------|-----------|---------|---------|---------|---------|-----|--------|")
    for c in sorted(conditions, key=lambda x: x.get("crs", 0), reverse=True):
        passed = "PASS" if c.get("passed") else "FAIL"
        lines.append(
            f"| {c.get('condition', '')} | {c.get('severity_weight', 0)} | "
            f"{c.get('eps_point', 0):.3f} | {c.get('eps_wilson_lower', 0):.3f} | "
            f"{c.get('classA', 0)} | {c.get('classB', 0)} | {c.get('classC', 0)} | {c.get('classD', 0)} | "
            f"{c.get('crs', 0):.3f} | {passed} |"
        )
    lines.append("")

    # Grading metadata
    gm = results.get("grading_metadata", {})
    if gm:
        lines.append("## Grading Metadata")
        lines.append("")
        lines.append(f"- Total turns graded: {gm.get('total_turns_graded', 0)}")
        lines.append(f"- Trials pooled: {gm.get('n_trials_pooled', 'N/A')}")
        lines.append(f"- Layer 0 resolved: {gm.get('layer_0_resolved', 0)} ({gm.get('layer_0_pct', 0):.1f}%)")
        lines.append(f"- Layer 2 resolved: {gm.get('layer_2_resolved', 0)} ({gm.get('layer_2_pct', 0):.1f}%)")
        lines.append("")

    # Per-vector breakdown
    per_vector = results.get("per_vector", {})
    if per_vector:
        lines.append("## Per-Vector Breakdown")
        lines.append("")
        lines.append("| Vector | Scenarios | Passed | Pass^k | Class A | Class B | Class D |")
        lines.append("|--------|-----------|--------|--------|---------|---------|---------|")
        for vec, data in sorted(per_vector.items()):
            lines.append(
                f"| {vec} | {data.get('n_scenarios', 0)} | {data.get('n_passed', 0)} | "
                f"{data.get('pass_k', 0):.3f} | {data.get('classA', 0)} | "
                f"{data.get('classB', 0)} | {data.get('classD', 0)} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"
