"""Dashboard Generator.

Reads results/index.yaml + CEIS result files and generates a self-contained
static HTML dashboard with SVG charts, or a markdown summary.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml

# Friendly model names for display (matches generate_leaderboard.py)
MODEL_DISPLAY = {
    "gpt-5.2": "GPT-5.2",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-6": "Claude Opus 4.6",
}


def _display_model(model_id: str) -> str:
    return MODEL_DISPLAY.get(model_id, model_id)


def _load_results_index(results_dir: Path) -> list[dict]:
    """Load experiments from results/index.yaml."""
    index_path = results_dir / "index.yaml"
    if not index_path.exists():
        return []
    with open(index_path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("experiments", [])


def _load_ceis_results(results_dir: Path) -> list[dict]:
    """Find and load all ceis_results.json files under results_dir."""
    results = []
    for p in sorted(results_dir.rglob("ceis_results.json")):
        try:
            with open(p) as f:
                data = json.load(f)
            data["_source_path"] = str(p.relative_to(results_dir))
            results.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _svg_bar(
    values: list[tuple[str, float, str]], width: int = 400, height: int = 200
) -> str:
    """Generate an SVG bar chart.

    values: list of (label, value, color) tuples.
    """
    if not values:
        return "<p>No data</p>"

    max_val = max(v for _, v, _ in values) or 1
    bar_width = max(20, (width - 60) // len(values))
    chart_height = height - 40

    parts = [
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
    ]
    parts.append(f'<rect width="{width}" height="{height}" fill="#f8f9fa" rx="4"/>')

    for i, (label, val, color) in enumerate(values):
        bar_h = (val / max_val) * (chart_height - 20) if max_val > 0 else 0
        x = 40 + i * (bar_width + 4)
        y = chart_height - bar_h
        parts.append(
            f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" fill="{color}" rx="2"/>'
        )
        parts.append(
            f'<text x="{x + bar_width // 2}" y="{chart_height + 14}" text-anchor="middle" font-size="10">{label}</text>'
        )
        parts.append(
            f'<text x="{x + bar_width // 2}" y="{y - 4}" text-anchor="middle" font-size="10">{val:.0f}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def generate_dashboard_markdown(
    results_dir: Path | str, output: Path | str | None = None
) -> str:
    """Generate a markdown dashboard summary.

    Reads results/index.yaml and produces four sections:
    1. Model × corpus matrix (best Pass^k per combo)
    2. Trendlines (delta across runs for same model/corpus/mode)
    3. Mitigation lift table (baseline → intervention deltas)
    4. Residual risk summary (combos where no run has Pass^k >= 0.70)

    Returns the markdown string. Optionally writes to file.
    """
    results_dir = Path(results_dir)
    experiments = _load_results_index(results_dir)

    sections: list[str] = ["# LostBench Dashboard\n"]

    # ── Section 1: Model × Corpus Matrix ──
    sections.append("## Model × Corpus Matrix\n")
    sections.append("Best Pass^k for each (model, corpus) combination.\n")

    # Group by (model, corpus), track best pass_k
    matrix: dict[str, dict[str, tuple[float, int, int]]] = defaultdict(dict)
    for exp in experiments:
        model = exp.get("model", "")
        corpus = exp.get("corpus", exp.get("experiment", ""))
        pk = exp.get("pass_k")
        if not isinstance(pk, (int, float)):
            continue
        n_trials = exp.get("n_trials", 0)
        scenarios = exp.get("scenarios", 0)
        existing = matrix[model].get(corpus)
        if existing is None or pk > existing[0]:
            matrix[model][corpus] = (pk, n_trials, scenarios)

    if matrix:
        all_corpora = sorted(
            {c for m in matrix.values() for c in m}, key=lambda c: c.lower()
        )
        header = "| Model | " + " | ".join(all_corpora) + " |"
        sep = "|-------" + "|--------" * len(all_corpora) + "|"
        sections.append(header)
        sections.append(sep)
        for model in sorted(matrix.keys()):
            cells = []
            for corpus in all_corpora:
                entry = matrix[model].get(corpus)
                if entry:
                    pk, nt, sc = entry
                    cells.append(f"{pk:.3f} (n={nt}, {sc}s)")
                else:
                    cells.append("-")
            sections.append(f"| {_display_model(model)} | " + " | ".join(cells) + " |")
        sections.append("")

    # ── Section 2: Trendlines ──
    sections.append("## Trendlines\n")
    sections.append(
        "Runs for the same (model, corpus, mode) sorted by date. Delta shown for consecutive runs.\n"
    )

    trends: dict[tuple[str, str, str], list[tuple[str, float]]] = defaultdict(list)
    for exp in experiments:
        model = exp.get("model", "")
        corpus = exp.get("corpus", exp.get("experiment", ""))
        mode = exp.get("mode", "baseline")
        pk = exp.get("pass_k")
        dt = exp.get("date", "")
        if isinstance(pk, (int, float)):
            trends[(model, corpus, mode)].append((dt, pk))

    has_trends = False
    for key in sorted(trends.keys()):
        runs = sorted(trends[key], key=lambda r: r[0])
        if len(runs) < 2:
            continue
        if not has_trends:
            sections.append("| Model | Corpus | Mode | Date | Pass^k | Delta |")
            sections.append("|-------|--------|------|------|--------|-------|")
            has_trends = True
        model, corpus, mode = key
        for i, (dt, pk) in enumerate(runs):
            delta = ""
            if i > 0:
                d = pk - runs[i - 1][1]
                delta = f"{d:+.3f}"
            sections.append(
                f"| {_display_model(model)} | {corpus} | {mode} | {dt} | {pk:.3f} | {delta} |"
            )

    if not has_trends:
        sections.append("No (model, corpus, mode) combinations with multiple runs.\n")
    sections.append("")

    # ── Section 3: Mitigation Lift Table ──
    sections.append("## Mitigation Lift\n")
    sections.append(
        "For 2x2 and adversarial-2x2 experiments: lift from each intervention vs. baseline.\n"
    )

    lift_exps = [
        e for e in experiments if e.get("experiment") in ("2x2", "adversarial-2x2")
    ]

    # Group by (model, corpus)
    lift_groups: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for exp in lift_exps:
        model = exp.get("model", "")
        corpus = exp.get("corpus", exp.get("experiment", ""))
        mode = exp.get("mode", "baseline")
        pk = exp.get("pass_k")
        if isinstance(pk, (int, float)):
            lift_groups[(model, corpus)][mode] = pk

    if lift_groups:
        sections.append(
            "| Model | Corpus | Baseline | + Preamble | + Enforcement | + Wrapper | Best Lift |"
        )
        sections.append(
            "|-------|--------|----------|------------|---------------|-----------|-----------|"
        )
        for model, corpus in sorted(lift_groups.keys()):
            modes = lift_groups[(model, corpus)]
            base = modes.get("baseline")
            if base is None:
                continue
            preamble = modes.get("preamble_only")
            enforce = modes.get("enforce_only")
            wrapper = modes.get("full_wrapper")

            def _fmt_lift(val: float | None) -> str:
                if val is None:
                    return "-"
                delta = val - base
                return f"{val:.3f} ({delta:+.3f})"

            lifts = [v - base for v in [preamble, enforce, wrapper] if v is not None]
            best = f"{max(lifts):+.3f}" if lifts else "-"

            sections.append(
                f"| {_display_model(model)} | {corpus} | {base:.3f} | "
                f"{_fmt_lift(preamble)} | {_fmt_lift(enforce)} | "
                f"{_fmt_lift(wrapper)} | {best} |"
            )
        sections.append("")

    # ── Section 4: Residual Risk Summary ──
    sections.append("## Residual Risk\n")
    sections.append(
        "Model × corpus combinations where no run achieves Pass^k >= 0.70.\n"
    )

    # Build best pass_k per (model, corpus)
    best_pk: dict[tuple[str, str], float] = {}
    for exp in experiments:
        model = exp.get("model", "")
        corpus = exp.get("corpus", exp.get("experiment", ""))
        pk = exp.get("pass_k")
        if isinstance(pk, (int, float)):
            key = (model, corpus)
            best_pk[key] = max(best_pk.get(key, 0), pk)

    at_risk = [(k, v) for k, v in sorted(best_pk.items()) if v < 0.70]
    if at_risk:
        sections.append("| Model | Corpus | Best Pass^k |")
        sections.append("|-------|--------|-------------|")
        for (model, corpus), pk in at_risk:
            sections.append(f"| {_display_model(model)} | {corpus} | {pk:.3f} |")
    else:
        sections.append(
            "All (model, corpus) combinations have at least one run with Pass^k >= 0.70."
        )
    sections.append("")

    md = "\n".join(sections)

    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md)

    return md


def generate_dashboard(results_dir: Path | str, output: Path | str) -> None:
    """Generate a self-contained HTML dashboard.

    Reads results/index.yaml and all ceis_results.json files.
    Generates static HTML with SVG charts and tables.
    """
    results_dir = Path(results_dir)
    output = Path(output)

    experiments = _load_results_index(results_dir)
    ceis_results = _load_ceis_results(results_dir)

    html = [
        "<!DOCTYPE html>",
        "<html><head>",
        "<meta charset='utf-8'>",
        "<title>LostBench Adversarial Dashboard</title>",
        "<style>",
        "* { box-sizing: border-box; }",
        "body { font-family: system-ui, sans-serif; margin: 0; padding: 20px; background: #f0f2f5; }",
        "h1 { color: #1a1a2e; border-bottom: 2px solid #e63946; padding-bottom: 8px; }",
        "h2 { color: #16213e; margin-top: 30px; }",
        ".grid { display: flex; flex-wrap: wrap; gap: 20px; }",
        ".card { background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); flex: 1; min-width: 300px; }",
        "table { border-collapse: collapse; width: 100%; margin: 10px 0; }",
        "th, td { border: 1px solid #dee2e6; padding: 8px 12px; text-align: left; font-size: 13px; }",
        "th { background: #343a40; color: white; }",
        "tr:nth-child(even) { background: #f8f9fa; }",
        ".pass { color: #28a745; font-weight: bold; }",
        ".fail { color: #dc3545; font-weight: bold; }",
        ".metric { font-size: 36px; font-weight: bold; color: #1a1a2e; }",
        ".metric-label { font-size: 14px; color: #6c757d; }",
        ".status-active { background: #dc3545; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; }",
        ".status-mitigated { background: #ffc107; color: black; padding: 2px 8px; border-radius: 4px; font-size: 11px; }",
        ".status-resolved { background: #28a745; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; }",
        "</style>",
        "</head><body>",
        "<h1>LostBench Adversarial Dashboard</h1>",
    ]

    # Summary metrics
    total_experiments = len(experiments)
    total_ceis = len(ceis_results)
    models_tested = sorted(set(e.get("model", "") for e in experiments))

    html.append("<div class='grid'>")
    html.append(
        f"<div class='card'><div class='metric'>{total_experiments}</div><div class='metric-label'>Total Experiments</div></div>"
    )
    html.append(
        f"<div class='card'><div class='metric'>{total_ceis}</div><div class='metric-label'>CEIS Evaluations</div></div>"
    )
    html.append(
        f"<div class='card'><div class='metric'>{len(models_tested)}</div><div class='metric-label'>Models Tested</div></div>"
    )
    html.append("</div>")

    # ERS by model+mode table
    html.append("<h2>ERS by Experiment</h2>")
    html.append("<div class='card'>")
    html.append(
        "<table><tr><th>Model</th><th>Corpus</th><th>Mode</th><th>n_trials</th><th>Pass^k</th><th>ERS</th><th>Class A</th><th>Date</th></tr>"
    )
    for exp in experiments:
        model = exp.get("model", "")
        corpus = exp.get("corpus", exp.get("experiment", ""))
        mode = exp.get("mode", "baseline")
        n_trials = exp.get("n_trials", "")
        pass_k = exp.get("pass_k", "")
        ers = exp.get("ers", "")
        class_a = exp.get("class_a", "")
        dt = exp.get("date", "")
        pk_str = f"{pass_k:.3f}" if isinstance(pass_k, float) else str(pass_k)
        cls = (
            "pass"
            if isinstance(pass_k, float) and pass_k >= 0.6
            else "fail"
            if isinstance(pass_k, float)
            else ""
        )
        html.append(
            f"<tr><td>{model}</td><td>{corpus}</td><td>{mode}</td><td>{n_trials}</td><td class='{cls}'>{pk_str}</td><td>{ers}</td><td>{class_a}</td><td>{dt}</td></tr>"
        )
    html.append("</table></div>")

    # ERS bar chart by model
    html.append("<h2>ERS by Model (Best Result)</h2>")
    html.append("<div class='card'>")
    model_best_ers: dict[str, float] = {}
    for exp in experiments:
        m = exp.get("model", "")
        e = exp.get("ers")
        if isinstance(e, (int, float)):
            model_best_ers[m] = max(model_best_ers.get(m, 0), e)
    colors = ["#e63946", "#457b9d", "#2a9d8f", "#e9c46a", "#264653", "#f4a261"]
    bars = [
        (m[:15], v, colors[i % len(colors)])
        for i, (m, v) in enumerate(sorted(model_best_ers.items()))
    ]
    html.append(_svg_bar(bars, width=max(400, len(bars) * 80), height=220))
    html.append("</div>")

    # Failure class distribution from CEIS results
    if ceis_results:
        html.append("<h2>Failure Class Distribution</h2>")
        html.append("<div class='card'>")
        html.append(
            "<table><tr><th>Source</th><th>Model</th><th>ERS</th><th>Class A</th><th>Class B</th><th>Class C</th><th>Class D</th></tr>"
        )
        for cr in ceis_results:
            meta = cr.get("meta", {})
            agg = cr.get("aggregate", {})
            html.append(
                f"<tr><td>{cr.get('_source_path', '')}</td>"
                f"<td>{meta.get('model_id', '')}</td>"
                f"<td>{agg.get('ERS', '')}</td>"
                f"<td>{agg.get('total_classA_failures', 0)}</td>"
                f"<td>{agg.get('total_classB_failures', 0)}</td>"
                f"<td>{agg.get('total_classC_failures', 0)}</td>"
                f"<td>{agg.get('total_classD_failures', 0)}</td></tr>"
            )
        html.append("</table></div>")

    html.append(
        "<p style='margin-top:30px;color:#6c757d;font-size:12px;'>Generated by LostBench dashboard tool</p>"
    )
    html.append("</body></html>")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(html))
