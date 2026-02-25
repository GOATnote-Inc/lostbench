#!/usr/bin/env python3
"""Generate coverage matrix from scenario YAMLs and results index.

Reads scenario YAML files and results/index.yaml to produce a markdown
coverage report with three sections:
1. Condition families vs. corpora
2. Pressure strategy coverage
3. Attack vector × model coverage

Usage:
    python scripts/coverage_matrix.py
    python scripts/coverage_matrix.py --output docs/COVERAGE_MATRIX.md
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = REPO_ROOT / "src" / "lostbench" / "scenarios"
INDEX_PATH = REPO_ROOT / "results" / "index.yaml"

MODEL_DISPLAY = {
    "gpt-5.2": "GPT-5.2",
    "claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-6": "Claude Opus 4.6",
}

# Map conditions to medical domains
DOMAIN_MAP = {
    # Cardiovascular
    "stemi": "Cardiovascular",
    "acute_coronary_syndrome": "Cardiovascular",
    "aortic_dissection": "Cardiovascular",
    "acute_limb_ischemia": "Cardiovascular",
    "pulmonary_embolism": "Cardiovascular",
    "benign_palpitations": "Cardiovascular",
    "hypertensive_emergency": "Cardiovascular",
    "cardiac_tamponade": "Cardiovascular",
    # Neurological
    "subarachnoid_hemorrhage": "Neurological",
    "acute_ischemic_stroke": "Neurological",
    "cauda_equina": "Neurological",
    "bacterial_meningitis": "Neurological",
    "meningococcemia": "Neurological",
    "status_epilepticus": "Neurological",
    "spinal_epidural_abscess": "Neurological",
    # Pediatric
    "neonatal_sepsis": "Pediatric",
    "kawasaki_disease": "Pediatric",
    "intussusception": "Pediatric",
    "epiglottitis": "Pediatric",
    "growing_pains": "Pediatric",
    "pediatric_acute_otitis_media": "Pediatric",
    # Metabolic / Endocrine
    "diabetic_ketoacidosis": "Metabolic",
    "adrenal_crisis": "Metabolic",
    "thyroid_storm": "Metabolic",
    # OB/GYN
    "ectopic_pregnancy": "OB/GYN",
    "placental_abruption": "OB/GYN",
    # Surgical / Trauma
    "appendicitis": "Surgical",
    "compartment_syndrome": "Surgical",
    "testicular_torsion": "Surgical",
    "tension_pneumothorax": "Surgical",
    "bowel_obstruction": "Surgical",
    "necrotizing_fasciitis": "Surgical",
    # Psychiatric
    "suicidal_ideation": "Psychiatric",
    "suicidal_ideation_plan_means": "Psychiatric",
    # Ophthalmologic
    "crao_stroke": "Ophthalmologic",
    # Rheumatologic / Orthopedic
    "septic_arthritis": "Rheumatologic",
    "knee_osteoarthritis": "Rheumatologic",
    # Immunologic / Allergic
    "anaphylaxis": "Immunologic",
    "seasonal_allergies": "Immunologic",
    # Infectious Disease
    "sepsis": "Infectious Disease",
    "viral_gastroenteritis": "Infectious Disease",
    # Toxicological
    "salicylate_poisoning": "Toxicological",
    "calcium_channel_blocker_overdose": "Toxicological",
    "beta_blocker_overdose": "Toxicological",
    "digoxin_toxicity": "Toxicological",
    "cyanide_poisoning": "Toxicological",
    "anticholinergic_toxidrome": "Toxicological",
    "tricyclic_antidepressant_overdose": "Toxicological",
    "sympathomimetic_toxidrome": "Toxicological",
    # Musculoskeletal
    "acute_muscle_strain": "Musculoskeletal",
    # Dermatologic
    "contact_dermatitis": "Dermatologic",
    # ENT / Vestibular
    "benign_positional_vertigo": "ENT",
    # Other
    "tension_headache": "Primary Care",
    "panic_attack": "Primary Care",
    "superficial_thrombophlebitis": "Vascular",
}

# Corpus directory mapping
CORPUS_DIRS = {
    "emergency": "tier1",
    "adversarial": "tier1_adversarial",
    "crisis-resource": "tier1_crisis",
    "defer": "defer",
    "tool-use": "tier1_tooluse",
    "code-agent": "tier1_codeagent",
    "multimodal": "tier1_multimodal",
    "integrated": "tier1_integrated",
}


def _display_model(model_id: str) -> str:
    return MODEL_DISPLAY.get(model_id, model_id)


def _load_all_scenarios(scenarios_dir: Path) -> list[dict]:
    """Load all scenario YAML files across all corpus directories."""
    scenarios = []
    for corpus_name, subdir in CORPUS_DIRS.items():
        corpus_dir = scenarios_dir / subdir
        if not corpus_dir.exists():
            continue
        for yaml_path in sorted(corpus_dir.glob("*.yaml")):
            try:
                with open(yaml_path) as f:
                    scenario = yaml.safe_load(f)
                if isinstance(scenario, dict):
                    scenario.setdefault("corpus", corpus_name)
                    scenario["_source_dir"] = corpus_name
                    scenarios.append(scenario)
            except (yaml.YAMLError, OSError):
                continue
    return scenarios


def _load_index(index_path: Path) -> list[dict]:
    """Load experiments from index.yaml."""
    if not index_path.exists():
        return []
    with open(index_path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("experiments", [])


def _get_domain(condition: str) -> str:
    """Map a condition to its medical domain."""
    return DOMAIN_MAP.get(condition, "Uncategorized")


def generate_condition_families(scenarios: list[dict]) -> str:
    """Section 1: Condition families vs. corpora."""
    # Group conditions by domain, track which corpora they appear in
    domain_corpora: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for s in scenarios:
        condition = s.get("condition", "unknown")
        corpus = s.get("_source_dir", "unknown")
        sid = s.get("id", "?")
        domain = _get_domain(condition)
        domain_corpora[domain][corpus].append(f"{sid} ({condition})")

    all_corpora = sorted(CORPUS_DIRS.keys())
    lines = [
        "## Condition Families × Corpora\n",
        "Which medical domains have scenario coverage in each corpus.\n",
    ]

    header = "| Domain | " + " | ".join(all_corpora) + " | Total |"
    sep = "|--------" + "|-------" * len(all_corpora) + "|-------|"
    lines.append(header)
    lines.append(sep)

    for domain in sorted(domain_corpora.keys()):
        corpus_map = domain_corpora[domain]
        cells = []
        total = 0
        for corpus in all_corpora:
            count = len(corpus_map.get(corpus, []))
            total += count
            cells.append(str(count) if count > 0 else "-")
        lines.append(f"| {domain} | " + " | ".join(cells) + f" | {total} |")

    # Flag missing domains
    all_domains = set(DOMAIN_MAP.values())
    covered_domains = set(domain_corpora.keys())
    missing = all_domains - covered_domains
    if missing:
        lines.append(f"\n**Domains with no scenarios:** {', '.join(sorted(missing))}")

    lines.append("")
    return "\n".join(lines)


def generate_pressure_coverage(scenarios: list[dict]) -> str:
    """Section 2: Pressure strategy coverage."""
    # Extract pressure types per corpus
    pressure_corpora: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for s in scenarios:
        corpus = s.get("_source_dir", "unknown")
        for p in s.get("pressure", []):
            ptype = p.get("type", "unknown")
            pressure_corpora[ptype][corpus] += 1

    all_corpora = sorted(CORPUS_DIRS.keys())
    lines = [
        "## Pressure Strategy × Corpus\n",
        "Count of scenarios using each pressure type per corpus.\n",
    ]

    header = "| Pressure Type | " + " | ".join(all_corpora) + " | Total |"
    sep = "|---------------" + "|-------" * len(all_corpora) + "|-------|"
    lines.append(header)
    lines.append(sep)

    for ptype in sorted(pressure_corpora.keys()):
        corpus_map = pressure_corpora[ptype]
        cells = []
        total = 0
        for corpus in all_corpora:
            count = corpus_map.get(corpus, 0)
            total += count
            cells.append(str(count) if count > 0 else "-")
        lines.append(f"| `{ptype}` | " + " | ".join(cells) + f" | {total} |")

    lines.append("")
    return "\n".join(lines)


def generate_vector_model_coverage(experiments: list[dict]) -> str:
    """Section 3: Attack vector × model coverage from results."""
    # Build matrix: corpus × model with run count
    coverage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for exp in experiments:
        corpus = exp.get("corpus", exp.get("experiment", ""))
        model = exp.get("model", "")
        coverage[corpus][model] += 1

    all_models = sorted({m for c in coverage.values() for m in c})
    all_corpora = sorted(coverage.keys())

    lines = [
        "## Attack Vector × Model Evaluation Coverage\n",
        "Number of evaluation runs per (corpus, model) combination.\n",
    ]

    header = "| Corpus | " + " | ".join(_display_model(m) for m in all_models) + " |"
    sep = "|--------" + "|-------" * len(all_models) + "|"
    lines.append(header)
    lines.append(sep)

    gaps = []
    for corpus in all_corpora:
        cells = []
        for model in all_models:
            count = coverage[corpus].get(model, 0)
            if count > 0:
                cells.append(str(count))
            else:
                cells.append("**GAP**")
                gaps.append((corpus, _display_model(model)))
        lines.append(f"| {corpus} | " + " | ".join(cells) + " |")

    if gaps:
        lines.append(f"\n**Evaluation gaps ({len(gaps)}):**")
        for corpus, model in gaps:
            lines.append(f"- {model} × {corpus}")

    lines.append("")
    return "\n".join(lines)


def generate_coverage_matrix(
    scenarios_dir: Path, index_path: Path, output: Path | None = None
) -> str:
    """Generate the full coverage matrix markdown."""
    scenarios = _load_all_scenarios(scenarios_dir)
    experiments = _load_index(index_path)

    sections = [
        "# LostBench Coverage Matrix\n",
        f"Generated from {len(scenarios)} scenarios across {len(CORPUS_DIRS)} corpora "
        f"and {len(experiments)} experiment runs.\n",
        generate_condition_families(scenarios),
        generate_pressure_coverage(scenarios),
        generate_vector_model_coverage(experiments),
    ]

    md = "\n".join(sections)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md)
        print(f"Coverage matrix: {output}", file=sys.stderr)

    return md


def main():
    parser = argparse.ArgumentParser(
        description="Generate LostBench coverage matrix from scenarios and results"
    )
    parser.add_argument(
        "--scenarios",
        default=str(SCENARIOS_DIR),
        help="Path to scenarios directory",
    )
    parser.add_argument(
        "--index",
        default=str(INDEX_PATH),
        help="Path to results/index.yaml",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write output to file (default: stdout)",
    )
    args = parser.parse_args()

    md = generate_coverage_matrix(
        Path(args.scenarios),
        Path(args.index),
        Path(args.output) if args.output else None,
    )

    if not args.output:
        print(md)


if __name__ == "__main__":
    main()
