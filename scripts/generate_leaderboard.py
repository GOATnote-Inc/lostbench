#!/usr/bin/env python3
"""Generate leaderboard tables from results/index.yaml.

Reads the canonical results index and produces:
1. Baseline leaderboard (sorted by Pass^k descending)
2. 2x2 wrapper matrix (model × mode)
3. CEIS summary (if present)

Output: Markdown tables to stdout (pipe to file or use --update-readme).

Usage:
    python scripts/generate_leaderboard.py
    python scripts/generate_leaderboard.py --update-readme
    python scripts/generate_leaderboard.py --output leaderboard.md
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "results" / "index.yaml"
README_PATH = REPO_ROOT / "README.md"

# Friendly model names for display
MODEL_DISPLAY = {
    "gpt-5.2": "GPT-5.2",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-6": "Claude Opus 4.6",
    "grok-4-1-fast-reasoning-latest": "Grok 4.1 Reasoning",
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro",
}

MODE_ORDER = ["baseline", "preamble_only", "enforce_only", "full_wrapper"]
MODE_HEADERS = {
    "baseline": "Baseline",
    "preamble_only": "+ Preamble",
    "enforce_only": "+ Enforcement",
    "full_wrapper": "+ Full Wrapper",
}


def load_index(path: Path) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("experiments", [])


def display_model(model_id: str) -> str:
    return MODEL_DISPLAY.get(model_id, model_id)


def generate_baseline_table(experiments: list[dict]) -> str:
    """Baseline leaderboard sorted by Pass^k descending."""
    baselines = [
        e
        for e in experiments
        if e.get("experiment") == "2x2" and e.get("mode") == "baseline"
    ]
    baselines.sort(key=lambda e: e.get("pass_k", 0), reverse=True)

    if not baselines:
        return ""

    lines = [
        "### Emergency Persistence — Baseline (23 scenarios × 3 trials, LLM judge)",
        "",
        "| Model | Pass^k | ERS | Scenarios | Date |",
        "|-------|--------|-----|-----------|------|",
    ]
    for e in baselines:
        lines.append(
            f"| {display_model(e['model'])} "
            f"| {e['pass_k']:.3f} "
            f"| {e.get('ers', 'N/A')} "
            f"| {e['scenarios']} "
            f"| {e['date']} |"
        )
    return "\n".join(lines)


def generate_2x2_table(experiments: list[dict]) -> str:
    """2x2 wrapper matrix: model × mode."""
    runs = [e for e in experiments if e.get("experiment") == "2x2"]
    if not runs:
        return ""

    # Group by model
    models: dict[str, dict[str, float]] = {}
    for e in runs:
        model = e["model"]
        mode = e["mode"]
        if model not in models:
            models[model] = {}
        models[model][mode] = e.get("pass_k", 0)

    # Sort models by best pass_k descending
    model_order = sorted(
        models.keys(),
        key=lambda m: max(models[m].values()),
        reverse=True,
    )

    lines = [
        "### MSIW Wrapper 2x2 — Expanded Corpus (23 scenarios × 3 trials, LLM judge)",
        "",
        "| Model | " + " | ".join(MODE_HEADERS[m] for m in MODE_ORDER) + " |",
        "|-------" + "|------------" * len(MODE_ORDER) + "|",
    ]
    for model in model_order:
        cells = []
        best = max(models[model].values())
        for mode in MODE_ORDER:
            pk = models[model].get(mode)
            if pk is None:
                cells.append("-")
            elif pk == best and pk > 0:
                cells.append(f"**{pk:.3f}**")
            else:
                cells.append(f"{pk:.3f}")
        lines.append(f"| {display_model(model)} | " + " | ".join(cells) + " |")

    return "\n".join(lines)


def generate_emergency_baseline_table(experiments: list[dict]) -> str:
    """Cross-vendor emergency baseline (50 scenarios)."""
    baselines = [
        e
        for e in experiments
        if e.get("experiment") == "emergency-baseline"
    ]
    if not baselines:
        return ""

    baselines.sort(key=lambda e: e.get("pass_k", 0), reverse=True)

    lines = [
        "### Emergency Persistence — Cross-Vendor Baseline (50 scenarios × 3 trials, LLM judge)",
        "",
        "| Model | Pass^k | ERS | ERS 95% CI | Class A | Class D | Threshold |",
        "|-------|--------|-----|------------|---------|---------|-----------|",
    ]
    for e in baselines:
        ci = e.get("ers_ci", ["-", "-"])
        threshold = "PASS" if e.get("meets_threshold") else "FAIL"
        lines.append(
            f"| {display_model(e['model'])} "
            f"| {e['pass_k']:.3f} "
            f"| {e.get('ers', 'N/A')} "
            f"| [{ci[0]}, {ci[1]}] "
            f"| {e.get('class_a', 0)} "
            f"| {e.get('class_d', 0)} "
            f"| {threshold} |"
        )
    return "\n".join(lines)


def generate_28new_table(experiments: list[dict]) -> str:
    """28 new MCI/HALO/procedural scenarios."""
    entries = [
        e
        for e in experiments
        if e.get("experiment") == "emergency-28new"
    ]
    if not entries:
        return ""

    entries.sort(key=lambda e: e.get("pass_k", 0), reverse=True)

    lines = [
        "### MCI / HALO / Procedural Expansion (28 scenarios × 3 trials, LLM judge)",
        "",
        "| Model | Pass^k | ERS | ERS 95% CI | Class A | Class D | Threshold |",
        "|-------|--------|-----|------------|---------|---------|-----------|",
    ]
    for e in entries:
        ci = e.get("ers_ci", ["-", "-"])
        threshold = "PASS" if e.get("meets_threshold") else "FAIL"
        lines.append(
            f"| {display_model(e['model'])} "
            f"| {e['pass_k']:.3f} "
            f"| {e.get('ers', 'N/A')} "
            f"| [{ci[0]}, {ci[1]}] "
            f"| {e.get('class_a', 0)} "
            f"| {e.get('class_d', 0)} "
            f"| {threshold} |"
        )
    return "\n".join(lines)


def generate_ceis_table(experiments: list[dict]) -> str:
    """CEIS deep-dive results."""
    ceis = [e for e in experiments if e.get("experiment") == "ceis-n5"]
    if not ceis:
        return ""

    lines = [
        "### CEIS Deep Dive",
        "",
        "| Model | Mode | Trials | ERS | ERS CI | Class A | Threshold |",
        "|-------|------|--------|-----|--------|---------|-----------|",
    ]
    for e in ceis:
        ci = e.get("ers_ci", ["-", "-"])
        threshold = "PASS" if e.get("meets_threshold") else "FAIL"
        lines.append(
            f"| {display_model(e['model'])} "
            f"| {e['mode']} "
            f"| {e['n_trials']} "
            f"| {e['ers']} "
            f"| [{ci[0]}, {ci[1]}] "
            f"| {e.get('class_a', 0)} "
            f"| {threshold} |"
        )
    return "\n".join(lines)


def generate_full_leaderboard(experiments: list[dict]) -> str:
    sections = [
        generate_emergency_baseline_table(experiments),
        generate_28new_table(experiments),
        generate_baseline_table(experiments),
        generate_2x2_table(experiments),
        generate_ceis_table(experiments),
    ]
    # Filter empty sections
    sections = [s for s in sections if s]
    return "\n\n".join(sections) + "\n"


def update_readme(leaderboard_md: str, readme_path: Path) -> bool:
    """Replace leaderboard section in README between markers."""
    content = readme_path.read_text()

    start_marker = "## Leaderboard"
    # Find end marker: next ## heading or end of file
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(
            "WARNING: '## Leaderboard' marker not found in README.md", file=sys.stderr
        )
        return False

    # Find the next ## heading after the leaderboard
    rest = content[start_idx + len(start_marker) :]
    next_heading = re.search(r"\n## [^#]", rest)

    if next_heading:
        end_idx = start_idx + len(start_marker) + next_heading.start()
    else:
        end_idx = len(content)

    new_section = f"{start_marker}\n\n{leaderboard_md}\n"
    new_content = content[:start_idx] + new_section + content[end_idx:]

    if new_content == content:
        print("README.md leaderboard is already up to date.", file=sys.stderr)
        return False

    readme_path.write_text(new_content)
    print("README.md leaderboard updated.", file=sys.stderr)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate LostBench leaderboard from results index"
    )
    parser.add_argument("--index", default=str(INDEX_PATH), help="Path to index.yaml")
    parser.add_argument(
        "--output", default=None, help="Write output to file (default: stdout)"
    )
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="Update the Leaderboard section in README.md",
    )
    args = parser.parse_args()

    experiments = load_index(Path(args.index))
    leaderboard = generate_full_leaderboard(experiments)

    if args.update_readme:
        update_readme(leaderboard, README_PATH)
    elif args.output:
        Path(args.output).write_text(leaderboard)
        print(f"Leaderboard written to {args.output}", file=sys.stderr)
    else:
        print(leaderboard)


if __name__ == "__main__":
    main()
