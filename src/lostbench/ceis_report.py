"""CEIS report generation — JSON artifact, executive summary, reproducibility bundle.

Generates structured output from CEIS evaluation results per spec Section 12.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from lostbench.ceis import CorpusGrade, RegressionResult
from lostbench.ceis_config import CEISConfig
from lostbench.scoring import condition_risk_score


def _generate_run_id(config: CEISConfig) -> str:
    """Generate a unique run ID: EG-{model}-{date}."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    model_short = config.model.replace("/", "-")[:20]
    return f"EG-{model_short}-{date_str}"


def generate_ceis_json(
    config: CEISConfig,
    corpus_grade: CorpusGrade,
    regression_result: RegressionResult | None = None,
    *,
    run_id: str | None = None,
    corpus_hash: str = "",
    system_prompt_hash: str = "",
) -> dict:
    """Build the full CEIS JSON artifact per spec Section 12.1.

    Returns a dict suitable for json.dump().
    """
    if run_id is None:
        run_id = _generate_run_id(config)

    timestamp = datetime.now(timezone.utc).isoformat()

    artifact: dict = {
        "meta": {
            "ceis_version": "0.2",
            "corpus_version": f"{config.corpus}-v1",
            "corpus_hash": corpus_hash,
            "run_id": run_id,
            "timestamp": timestamp,
            "model_id": config.model,
            "provider": config.provider,
            "temperature": config.temperature,
            "seed": config.seed,
            "n_trials": config.n_trials,
            "n_scenarios": len(corpus_grade.conditions),
            "system_prompt_hash": system_prompt_hash,
            "mode": "as_deployed",
        },
        "aggregate": {
            "ERS": corpus_grade.ers,
            "ERS_bootstrap_ci": list(corpus_grade.ers_bootstrap_ci),
            "pass_k": corpus_grade.pass_k,
            "harm_weighted_pass": corpus_grade.harm_weighted_pass,
            "total_classA_failures": corpus_grade.total_classA,
            "total_classB_failures": corpus_grade.total_classB,
            "total_classC_failures": corpus_grade.total_classC,
            "total_classD_failures": corpus_grade.total_classD,
            "total_drift_events": corpus_grade.total_drift,
            "meets_threshold": corpus_grade.meets_threshold,
            "threshold_failures": corpus_grade.threshold_failures,
        },
        "conditions": [],
        "grading_metadata": corpus_grade.grading_metadata,
    }

    for c in corpus_grade.conditions:
        crs, _ = condition_risk_score(
            wilson_lower=c.eps_wilson_lower,
            classA_failures=c.classA,
            drift_count=c.drift_count,
            severity_weight=c.severity_weight,
            classD_flag=c.classD > 0,
        )
        artifact["conditions"].append(
            {
                "condition": c.condition,
                "scenario_id": c.scenario_id,
                "severity_weight": c.severity_weight,
                "initial_escalation_correct": c.initial_escalation_correct,
                "eps_point": c.eps_point,
                "eps_wilson_lower": c.eps_wilson_lower,
                "eps_wilson_upper": c.eps_wilson_upper,
                "n_required_turns": c.n_required_turns,
                "n_maintained_turns": c.n_maintained_turns,
                "drift_count": c.drift_count,
                "classA": c.classA,
                "classB": c.classB,
                "classC": c.classC,
                "classD": c.classD,
                "crs": round(crs, 3),
                "passed": c.passed,
                "failure_turns": c.failure_turns,
            }
        )

    # Per-vector breakdown (for adversarial expansion scenarios)
    vector_groups: dict[str, list] = {}
    for c in corpus_grade.conditions:
        # Look up vector from the condition's source scenario if available
        vector = getattr(c, "vector", None) or "unspecified"
        vector_groups.setdefault(vector, []).append(c)
    if len(vector_groups) > 1 or "unspecified" not in vector_groups:
        per_vector: dict[str, dict] = {}
        for vector, conditions_list in sorted(vector_groups.items()):
            n_total = len(conditions_list)
            n_passed = sum(1 for c in conditions_list if c.passed)
            pass_k = n_passed / n_total if n_total > 0 else 0.0
            class_a = sum(c.classA for c in conditions_list)
            class_b = sum(c.classB for c in conditions_list)
            class_c = sum(c.classC for c in conditions_list)
            class_d = sum(c.classD for c in conditions_list)
            per_vector[vector] = {
                "n_scenarios": n_total,
                "n_passed": n_passed,
                "pass_k": round(pass_k, 3),
                "classA": class_a,
                "classB": class_b,
                "classC": class_c,
                "classD": class_d,
            }
        artifact["per_vector"] = per_vector

    if regression_result:
        artifact["regression"] = {
            "prior_model_id": regression_result.prior_model_id,
            "prior_ers": regression_result.prior_ers,
            "ers_delta": regression_result.ers_delta,
            "regression_detected": regression_result.regression_detected,
            "per_condition_z": regression_result.per_condition_z,
            "new_classA_conditions": regression_result.new_classA_conditions,
            "regression_suite_failures": regression_result.regression_suite_failures,
        }

    return artifact


def generate_executive_summary(
    config: CEISConfig,
    corpus_grade: CorpusGrade,
    regression_result: RegressionResult | None = None,
    *,
    run_id: str = "",
) -> str:
    """Generate plain-text executive summary per spec Section 12.2."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Header
    lines = [
        "ESCALATION PERSISTENCE REPORT",
        f"Model: {config.model} | Corpus: {config.corpus} | Date: {date_str} | Run: {run_id}",
        "",
    ]

    # ERS and threshold
    ci = corpus_grade.ers_bootstrap_ci
    lines.append(
        f"ESCALATION RISK SCORE: {corpus_grade.ers} / 100 (95% CI: [{ci[0]:.0f}, {ci[1]:.0f}])"
    )
    threshold_str = "Meets" if corpus_grade.meets_threshold else "Does Not Meet"
    lines.append(f"THRESHOLD: {threshold_str}")

    if regression_result:
        reg_str = (
            "Detected" if regression_result.regression_detected else "Not Detected"
        )
        lines.append(f"REGRESSION: {reg_str} (vs {regression_result.prior_model_id})")
    else:
        lines.append("REGRESSION: No prior version provided")

    lines.append("")

    # Threshold failures
    if corpus_grade.threshold_failures:
        lines.append("THRESHOLD FAILURES:")
        for f in corpus_grade.threshold_failures:
            lines.append(f"- {f}")
        lines.append("")

    # Key metrics
    n_conditions = len([c for c in corpus_grade.conditions if c.severity_weight > 0])
    mean_eps_lower = 0.0
    if n_conditions > 0:
        mean_eps_lower = (
            sum(
                c.eps_wilson_lower
                for c in corpus_grade.conditions
                if c.severity_weight > 0
            )
            / n_conditions
        )

    lines.append("KEY METRICS:")
    lines.append(
        f"  Pass^k                  {corpus_grade.pass_k:.3f}    {n_conditions} conditions, {config.n_trials} trials"
    )
    lines.append(f"  Harm-weighted pass      {corpus_grade.harm_weighted_pass:.3f}")
    lines.append(
        f"  Mean EPS (Wilson lower) {mean_eps_lower:.3f}    {n_conditions} conditions"
    )
    lines.append(f"  Drift events            {corpus_grade.total_drift}")
    lines.append(f"  Class A failures        {corpus_grade.total_classA}")
    lines.append(f"  Class B failures        {corpus_grade.total_classB}")
    lines.append(f"  Class D failures        {corpus_grade.total_classD}")
    lines.append("")

    # Per-vector breakdown (if multiple vectors present)
    vector_groups: dict[str, list] = {}
    for c in corpus_grade.conditions:
        vector = getattr(c, "vector", None) or "unspecified"
        vector_groups.setdefault(vector, []).append(c)
    if len(vector_groups) > 1 or "unspecified" not in vector_groups:
        lines.append("PER-VECTOR BREAKDOWN:")
        for vector, conditions_list in sorted(vector_groups.items()):
            n_total = len(conditions_list)
            n_passed = sum(1 for c in conditions_list if c.passed)
            pass_k = n_passed / n_total if n_total > 0 else 0.0
            class_a = sum(c.classA for c in conditions_list)
            lines.append(
                f"  {vector:<25} Pass^k={pass_k:.3f}  ({n_passed}/{n_total})  Class A={class_a}"
            )
        lines.append("")

    # Conditions below threshold
    failed_conditions = [
        c for c in corpus_grade.conditions if not c.passed and c.severity_weight > 0
    ]
    if failed_conditions:
        lines.append("CONDITIONS BELOW THRESHOLD:")
        for c in failed_conditions:
            failure_classes = []
            if c.classA > 0:
                failure_classes.append(f"Class A x{c.classA}")
            if c.classB > 0:
                failure_classes.append(f"Class B x{c.classB}")
            if c.classC > 0:
                failure_classes.append(f"Class C x{c.classC}")
            if c.classD > 0:
                failure_classes.append(f"Class D x{c.classD}")
            failure_str = (
                ", ".join(failure_classes)
                if failure_classes
                else "no classified failures"
            )
            lines.append(
                f"  {c.condition} -- EPS lower={c.eps_wilson_lower:.2f}, {failure_str}"
            )
        lines.append("")

    # Regression detail
    if regression_result and regression_result.regression_detected:
        lines.append("REGRESSION DETAIL:")
        lines.append(
            f"  Prior ERS: {regression_result.prior_ers} -> "
            f"Current ERS: {corpus_grade.ers} "
            f"(delta = {regression_result.ers_delta})"
        )
        if regression_result.regressed_conditions:
            lines.append("  Conditions with significant regression (z < -1.96):")
            for cond in regression_result.regressed_conditions:
                z = regression_result.per_condition_z.get(cond, 0)
                lines.append(f"    {cond}: z = {z}")
        if regression_result.new_classA_conditions:
            lines.append(
                f"  New Class A failures: {', '.join(regression_result.new_classA_conditions)}"
            )
        if regression_result.regression_suite_failures:
            lines.append(
                f"  Regression suite failures: {', '.join(regression_result.regression_suite_failures)}"
            )
        lines.append("")

    # Methodology
    lines.append("METHODOLOGY:")
    lines.append(
        f"  Corpus: {config.corpus}, {len(corpus_grade.conditions)} scenarios, {config.n_trials} trials, seed={config.seed}"
    )
    lines.append(
        "  Grading: 3-layer hybrid (deterministic patterns -> cross-vendor LLM judge)"
    )
    lines.append(
        "  Scoring: Wilson 95% CI, scenario-level bootstrap (10,000 iterations)"
    )
    lines.append("  Regression: Two-proportion z-test, one-tailed, alpha=0.025")

    return "\n".join(lines) + "\n"


def generate_reproducibility_bundle(
    output_dir: str | Path,
    config: CEISConfig,
    artifact: dict,
    *,
    run_id: str | None = None,
) -> Path:
    """Write reproducibility bundle per spec Section 10.4.

    Creates:
        {run_id}/
            config.yaml         # Full config (sans API keys)
            config_hash.sha256
            corpus_hash.sha256
            results.json        # CEIS artifact
            report.txt          # Executive summary
    """
    import yaml

    if run_id is None:
        run_id = artifact.get("meta", {}).get("run_id", "unknown")

    bundle_dir = Path(output_dir) / run_id
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Config YAML (no secrets)
    config_dict = {
        "model": config.model,
        "provider": config.provider,
        "corpus": config.corpus,
        "n_trials": config.n_trials,
        "temperature": config.temperature,
        "seed": config.seed,
        "max_tokens": config.max_tokens,
        "wrapper_enabled": config.wrapper_enabled,
        "inject_preamble": config.inject_preamble,
        "output_formats": config.output_formats,
    }
    if config.judge_model:
        config_dict["judge_model"] = config.judge_model
    if config.conditions:
        config_dict["conditions"] = config.conditions

    config_yaml = yaml.dump(config_dict, default_flow_style=False)
    (bundle_dir / "config.yaml").write_text(config_yaml)

    # Config hash
    config_hash = hashlib.sha256(config_yaml.encode()).hexdigest()
    (bundle_dir / "config_hash.sha256").write_text(f"sha256:{config_hash}\n")

    # Corpus hash
    corpus_hash = artifact.get("meta", {}).get("corpus_hash", "")
    (bundle_dir / "corpus_hash.sha256").write_text(f"{corpus_hash}\n")

    # Results JSON
    results_path = bundle_dir / "results.json"
    with open(results_path, "w") as f:
        json.dump(artifact, f, indent=2)

    # Executive summary
    corpus_grade = _reconstruct_corpus_grade_for_summary(artifact)
    regression_result = _reconstruct_regression_for_summary(artifact)
    summary = generate_executive_summary(
        config,
        corpus_grade,
        regression_result,
        run_id=run_id,
    )
    (bundle_dir / "report.txt").write_text(summary)

    return bundle_dir


def _reconstruct_corpus_grade_for_summary(artifact: dict) -> CorpusGrade:
    """Reconstruct a minimal CorpusGrade from a CEIS JSON artifact for summary generation."""
    from lostbench.ceis import ScenarioGrade

    agg = artifact.get("aggregate", {})
    conditions = []
    for c in artifact.get("conditions", []):
        conditions.append(
            ScenarioGrade(
                scenario_id=c.get("scenario_id", ""),
                condition=c.get("condition", ""),
                severity_weight=c.get("severity_weight", 0.0),
                required_escalation_level=3,
                initial_escalation_correct=c.get("initial_escalation_correct", False),
                eps_point=c.get("eps_point", 0.0),
                eps_wilson_lower=c.get("eps_wilson_lower", 0.0),
                eps_wilson_upper=c.get("eps_wilson_upper", 0.0),
                n_required_turns=c.get("n_required_turns", 0),
                n_maintained_turns=c.get("n_maintained_turns", 0),
                drift_count=c.get("drift_count", 0),
                classA=c.get("classA", 0),
                classB=c.get("classB", 0),
                classC=c.get("classC", 0),
                classD=c.get("classD", 0),
                passed=c.get("passed", False),
            )
        )

    return CorpusGrade(
        ers=agg.get("ERS", 0),
        ers_bootstrap_ci=tuple(agg.get("ERS_bootstrap_ci", [0.0, 0.0])),
        pass_k=agg.get("pass_k", 0.0),
        harm_weighted_pass=agg.get("harm_weighted_pass", 0.0),
        total_classA=agg.get("total_classA_failures", 0),
        total_classB=agg.get("total_classB_failures", 0),
        total_classC=agg.get("total_classC_failures", 0),
        total_classD=agg.get("total_classD_failures", 0),
        total_drift=agg.get("total_drift_events", 0),
        meets_threshold=agg.get("meets_threshold", False),
        threshold_failures=agg.get("threshold_failures", []),
        conditions=conditions,
        grading_metadata=artifact.get("grading_metadata", {}),
    )


def _reconstruct_regression_for_summary(artifact: dict) -> RegressionResult | None:
    """Reconstruct RegressionResult from CEIS JSON artifact."""
    reg = artifact.get("regression")
    if not reg:
        return None
    return RegressionResult(
        prior_model_id=reg.get("prior_model_id", ""),
        prior_ers=reg.get("prior_ers", 0),
        ers_delta=reg.get("ers_delta", 0),
        regression_detected=reg.get("regression_detected", False),
        per_condition_z=reg.get("per_condition_z", {}),
        regressed_conditions=list(reg.get("per_condition_z", {}).keys()),
        new_classA_conditions=reg.get("new_classA_conditions", []),
        regression_suite_failures=reg.get("regression_suite_failures", []),
    )


# ---------------------------------------------------------------------------
# Failure Catalog Entry Generation (Pillar 6b — Exploit Lineage Tracking)
# ---------------------------------------------------------------------------


def generate_failure_catalog_entries(
    config: CEISConfig,
    corpus_grade: CorpusGrade,
    *,
    run_id: str = "",
) -> list[dict]:
    """Generate failure catalog entries for Class A failures discovered during CEIS evaluation.

    Each entry follows the schema defined in
    scribegoat2/governance/failure_catalog/schema.yaml.

    Only generates entries for Class A failures (critical escalation drops)
    in conditions with severity_weight >= 0.7. These are the safety-critical
    findings that require structured tracking and mitigation verification.

    Returns list of catalog entry dicts ready for YAML serialization.
    """
    entries = []
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for c in corpus_grade.conditions:
        if c.classA == 0 or c.severity_weight < 0.7:
            continue

        # Build failure turn detail
        failure_detail = []
        for ft in c.failure_turns:
            if ft.get("failure_class") == "A":
                detail = f"turn {ft['turn_index']}"
                if "trial" in ft:
                    detail += f" trial {ft['trial']}"
                detail += f" (level {ft['escalation_level']} vs required {ft['required_level']})"
                failure_detail.append(detail)

        entry = {
            "id": f"FM-AUTO-{run_id}-{c.scenario_id}"
            if run_id
            else f"FM-AUTO-{date_str}-{c.scenario_id}",
            "title": f"Class A escalation failure: {c.condition}",
            "discovered": date_str,
            "status": "open",
            "severity_esi": _severity_weight_to_esi(c.severity_weight),
            "category": "escalation_drift",
            "affected_models": [config.model],
            "description": (
                f"CEIS detected {c.classA} Class A failure(s) in {c.condition} "
                f"(severity_weight={c.severity_weight}). "
                f"EPS point={c.eps_point:.3f}, Wilson lower={c.eps_wilson_lower:.3f}. "
                f"Failures: {'; '.join(failure_detail)}."
            ),
            "trigger": (
                f"Run CEIS evaluation on {c.condition} with model {config.model}, "
                f"n_trials={config.n_trials}, seed={config.seed}."
            ),
            "evidence": [
                f"CEIS run {run_id}" if run_id else f"CEIS run {date_str}",
                f"Scenario {c.scenario_id}, condition {c.condition}",
            ],
            "clinical_impact": (
                f"Model drops from Level 3 (emergency) to Level 0-1 on {c.condition}. "
                f"Delayed treatment for this condition."
            ),
            "reproducibility": f"{c.classA}/{c.n_required_turns} turns ({c.classA / c.n_required_turns * 100:.1f}%)",
            "discovery_method": "ceis_eval",
            "ceis_class": "A",
            "conditions": [c.condition],
            "mitigation": "None",
            "mitigation_status": "untested",
        }
        entries.append(entry)

    return entries


def _severity_weight_to_esi(severity_weight: float) -> int:
    """Map CEIS severity_weight to ESI triage scale for catalog entries."""
    if severity_weight >= 1.0:
        return 1
    if severity_weight >= 0.8:
        return 2
    if severity_weight >= 0.5:
        return 3
    if severity_weight >= 0.3:
        return 4
    return 5


def format_run_log_entry(
    config: CEISConfig,
    corpus_grade: CorpusGrade,
    regression_result: RegressionResult | None = None,
    *,
    run_id: str = "",
    artifacts_dir: str = "",
    notes: str = "",
) -> str:
    """Format a single JSONL entry for run_log.jsonl per spec Section 12.3.

    Returns a JSON string (one line, no trailing newline).
    """
    entry = {
        "id": run_id or _generate_run_id(config),
        "ts": datetime.now(timezone.utc).isoformat(),
        "task": "ceis",
        "models": [config.model],
        "scorer": "3-layer-hybrid",
        "n_scenarios": len(corpus_grade.conditions),
        "n_trials": config.n_trials,
        "seed": config.seed,
        "temperature": config.temperature,
        "results": {
            config.model: {
                "ERS": corpus_grade.ers,
                "pass_k": corpus_grade.pass_k,
                "harm_weighted_pass": corpus_grade.harm_weighted_pass,
                "classA_failures": corpus_grade.total_classA,
                "meets_threshold": corpus_grade.meets_threshold,
                "regression_detected": (
                    regression_result.regression_detected if regression_result else None
                ),
            },
        },
        "artifacts_dir": artifacts_dir,
        "notes": notes,
    }
    return json.dumps(entry, separators=(",", ":"))
