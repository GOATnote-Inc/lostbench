"""Coverage Heatmap Generator.

Computes taxonomy x condition x model coverage matrix and generates
static HTML heatmaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class CoverageGap:
    """A taxonomy region with zero or low scenario coverage."""

    vector: str
    condition: str | None
    gap_type: str  # "no_scenario" | "no_results" | "untested_model"
    description: str


@dataclass
class CoverageMatrix:
    """Taxonomy x condition x model coverage."""

    vectors: list[str]
    conditions: list[str]
    models: list[str]
    # scenario_coverage[vector][condition] = scenario_id or None
    scenario_coverage: dict[str, dict[str, str | None]] = field(default_factory=dict)
    # result_coverage[vector][condition][model] = True/False
    result_coverage: dict[str, dict[str, dict[str, bool]]] = field(default_factory=dict)


def compute_coverage(
    taxonomy_path: Path | str,
    scenarios_dir: Path | str,
    results_dir: Path | str | None = None,
) -> CoverageMatrix:
    """Compute taxonomy x condition x model coverage.

    Args:
        taxonomy_path: Path to configs/attack_taxonomy.yaml
        scenarios_dir: Path to src/lostbench/scenarios/
        results_dir: Optional path to results/ for tested coverage
    """
    taxonomy_path = Path(taxonomy_path)
    scenarios_dir = Path(scenarios_dir)

    with open(taxonomy_path) as f:
        taxonomy = yaml.safe_load(f)

    vectors = []
    all_conditions: set[str] = set()
    scenario_coverage: dict[str, dict[str, str | None]] = {}

    for vec in taxonomy.get("vectors", []):
        vid = vec["id"]
        vectors.append(vid)
        conditions = vec.get("conditions_targeted", [])
        all_conditions.update(conditions)
        scenario_coverage[vid] = {}

        # Check which conditions have scenarios
        corpus_dir = scenarios_dir / Path(vec["corpus_dir"]).name
        scenario_files = list(corpus_dir.glob("*.yaml")) if corpus_dir.exists() else []

        # Load scenario conditions
        scenario_conditions: dict[str, str] = {}
        for sf in scenario_files:
            try:
                with open(sf) as f:
                    s = yaml.safe_load(f)
                if s and "condition" in s:
                    scenario_conditions[s["condition"]] = s.get("id", sf.stem)
            except Exception:
                continue

        for cond in conditions:
            scenario_coverage[vid][cond] = scenario_conditions.get(cond)

    conditions_list = sorted(all_conditions)

    # Result coverage
    models: set[str] = set()
    result_coverage: dict[str, dict[str, dict[str, bool]]] = {}

    if results_dir:
        results_dir = Path(results_dir)
        index_path = results_dir / "index.yaml"
        if index_path.exists():
            with open(index_path) as f:
                index = yaml.safe_load(f)
            for exp in index.get("experiments", []):
                model = exp.get("model", "")
                corpus = exp.get("corpus", "")
                models.add(model)

                # Map corpus to vector
                corpus_to_vector = {
                    "code-agent": "code-agent",
                    "tool-use": "tool-use",
                    "multimodal": "multimodal",
                    "integrated": "integrated",
                    "adversarial": "adversarial",
                    "emergency": "emergency",
                }
                vector = corpus_to_vector.get(corpus)
                if not vector:
                    continue

                result_coverage.setdefault(vector, {})
                # Mark all conditions for this vector as tested for this model
                for cond in taxonomy.get("vectors", [{}]):
                    if cond.get("id") == vector:
                        for c in cond.get("conditions_targeted", []):
                            result_coverage[vector].setdefault(c, {})
                            result_coverage[vector][c][model] = True
                        break

    return CoverageMatrix(
        vectors=vectors,
        conditions=conditions_list,
        models=sorted(models),
        scenario_coverage=scenario_coverage,
        result_coverage=result_coverage,
    )


def identify_gaps(matrix: CoverageMatrix) -> list[CoverageGap]:
    """Identify taxonomy regions with zero or low scenario coverage."""
    gaps: list[CoverageGap] = []

    for vector in matrix.vectors:
        vec_scenarios = matrix.scenario_coverage.get(vector, {})

        for condition in matrix.conditions:
            if condition not in vec_scenarios:
                continue

            # No scenario exists for this vector x condition
            if vec_scenarios[condition] is None:
                gaps.append(CoverageGap(
                    vector=vector,
                    condition=condition,
                    gap_type="no_scenario",
                    description=f"No scenario for {condition} under {vector}",
                ))
                continue

            # Scenario exists but no results
            vec_results = matrix.result_coverage.get(vector, {})
            cond_results = vec_results.get(condition, {})
            if not cond_results:
                gaps.append(CoverageGap(
                    vector=vector,
                    condition=condition,
                    gap_type="no_results",
                    description=f"Scenario exists for {condition} under {vector} but untested",
                ))
                continue

            # Check for untested models
            for model in matrix.models:
                if model not in cond_results:
                    gaps.append(CoverageGap(
                        vector=vector,
                        condition=condition,
                        gap_type="untested_model",
                        description=f"{condition} under {vector} not tested on {model}",
                    ))

    return gaps


def generate_heatmap_html(matrix: CoverageMatrix, output: Path | str) -> None:
    """Generate a self-contained static HTML heatmap.

    No JS framework dependencies -- pure HTML + inline CSS.
    """
    output = Path(output)

    html_parts = [
        "<!DOCTYPE html>",
        "<html><head>",
        "<meta charset='utf-8'>",
        "<title>LostBench Coverage Heatmap</title>",
        "<style>",
        "body { font-family: system-ui, sans-serif; margin: 20px; background: #f8f9fa; }",
        "h1 { color: #1a1a2e; }",
        "h2 { color: #16213e; margin-top: 30px; }",
        "table { border-collapse: collapse; margin: 10px 0; }",
        "th, td { border: 1px solid #dee2e6; padding: 6px 10px; text-align: center; font-size: 13px; }",
        "th { background: #343a40; color: white; }",
        ".covered { background: #28a745; color: white; }",
        ".partial { background: #ffc107; color: black; }",
        ".missing { background: #dc3545; color: white; }",
        ".na { background: #6c757d; color: white; }",
        ".gap-list { margin: 10px 0; }",
        ".gap-item { padding: 4px 8px; margin: 2px 0; background: #fff3cd; border-left: 3px solid #ffc107; }",
        ".gap-item.critical { background: #f8d7da; border-left-color: #dc3545; }",
        "</style>",
        "</head><body>",
        "<h1>LostBench Coverage Heatmap</h1>",
    ]

    # Scenario coverage table
    html_parts.append("<h2>Scenario Coverage (Vector x Condition)</h2>")
    html_parts.append("<table><tr><th>Condition</th>")
    for v in matrix.vectors:
        html_parts.append(f"<th>{v}</th>")
    html_parts.append("</tr>")

    for cond in matrix.conditions:
        html_parts.append(f"<tr><td><b>{cond}</b></td>")
        for v in matrix.vectors:
            sid = matrix.scenario_coverage.get(v, {}).get(cond)
            if sid is None:
                # Check if this condition is even targeted by this vector
                if cond in matrix.scenario_coverage.get(v, {}):
                    html_parts.append("<td class='missing'>MISSING</td>")
                else:
                    html_parts.append("<td class='na'>—</td>")
            else:
                html_parts.append(f"<td class='covered'>{sid}</td>")
        html_parts.append("</tr>")
    html_parts.append("</table>")

    # Gaps
    gaps = identify_gaps(matrix)
    if gaps:
        html_parts.append("<h2>Coverage Gaps</h2>")
        html_parts.append("<div class='gap-list'>")
        for g in gaps:
            cls = "gap-item critical" if g.gap_type == "no_scenario" else "gap-item"
            html_parts.append(f"<div class='{cls}'>{g.description}</div>")
        html_parts.append("</div>")

    html_parts.append("<p><small>Generated by LostBench coverage tool</small></p>")
    html_parts.append("</body></html>")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(html_parts))
