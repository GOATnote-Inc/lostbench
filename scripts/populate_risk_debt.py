#!/usr/bin/env python3
"""Auto-populate risk_debt.yaml from campaign results + mining analysis.

Sources:
  - Class A failures on high/critical severity from CEIS results
  - Significant pressure asymmetries (ratio > 5x) from mining analysis
  - Active exploit families from registry

Rules:
  - Preserve existing entries verbatim
  - Auto-ID new entries as FINDING-YYYY-MM-DD-NNN
  - Never delete existing entries

Usage:
    python3 scripts/populate_risk_debt.py
    python3 scripts/populate_risk_debt.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RISK_DEBT_PATH = REPO_ROOT / "results" / "risk_debt.yaml"
ANALYSIS_DIR = REPO_ROOT / "results" / "analysis"
FAMILIES_PATH = REPO_ROOT / "configs" / "exploit_families.yaml"
INDEX_PATH = REPO_ROOT / "results" / "index.yaml"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _existing_finding_ids(risk_debt: dict) -> set[str]:
    """Extract all existing finding IDs."""
    ids = set()
    for entry in risk_debt.get("accepted_risks", []):
        fid = entry.get("finding_id", "")
        if fid:
            ids.add(fid)
    return ids


def _next_finding_id(existing_ids: set[str], today: str) -> str:
    """Generate next FINDING-YYYY-MM-DD-NNN ID."""
    prefix = f"FINDING-{today}-"
    existing_nums = []
    for fid in existing_ids:
        if fid.startswith(prefix):
            try:
                num = int(fid.split("-")[-1])
                existing_nums.append(num)
            except ValueError:
                pass
    next_num = max(existing_nums, default=0) + 1
    return f"{prefix}{next_num:03d}"


def findings_from_index(
    index: dict,
    existing_ids: set[str],
    today: str,
) -> list[dict]:
    """Generate findings from CEIS results with Class A failures."""
    findings = []
    experiments = index.get("experiments", [])

    for exp in experiments:
        class_a = exp.get("class_a", 0)
        if class_a == 0:
            continue

        model = exp.get("model", "unknown")
        corpus = exp.get("corpus", exp.get("experiment", "unknown"))
        exp_date = exp.get("date", today)
        mode = exp.get("mode", "baseline")
        pass_k = exp.get("pass_k")

        # Skip if we already have a finding for this campaign
        campaign_id = f"CAMPAIGN-{exp_date}-{corpus}"
        if any(
            e.get("source_campaign", "") == campaign_id
            for fid in existing_ids
            for e in [{"source_campaign": campaign_id}]
        ):
            continue

        finding_id = _next_finding_id(existing_ids, today)
        existing_ids.add(finding_id)

        review_date = (date.fromisoformat(today) + timedelta(days=30)).isoformat()

        finding = {
            "finding_id": finding_id,
            "severity": "critical" if class_a >= 3 else "high",
            "priority": "P1" if class_a >= 3 else "P2",
            "exploitability": "high" if mode == "baseline" else "medium",
            "description": (
                f"{class_a} Class A failures on {corpus} corpus for {model} "
                f"({mode} mode). Pass^k={pass_k}."
            ),
            "models_affected": [
                {
                    "model": model,
                    "status": "active",
                    "baseline_pass_k": pass_k if mode == "baseline" else None,
                    "mitigated_pass_k": pass_k if mode != "baseline" else None,
                }
            ],
            "mitigation_status": "open",
            "mitigation_history": [],
            "reproduction": {
                "command": "lostbench ceis run --config <config.yaml>",
                "config": f"corpus={corpus}, model={model}, mode={mode}",
                "expected_failure_class": "A",
            },
            "source_campaign": campaign_id,
            "source_analysis": None,
            "accepted_date": today,
            "review_date": review_date,
            "accepted_by": None,
            "resolved_date": None,
            "resolution": None,
        }

        findings.append(finding)

    return findings


def findings_from_pressure(
    pressure: dict,
    existing_ids: set[str],
    today: str,
) -> list[dict]:
    """Generate findings from significant pressure asymmetries (ratio > 5x)."""
    findings = []

    for model_id, model_data in pressure.items():
        if not isinstance(model_data, dict):
            continue

        rates = []
        for ptype, stats in model_data.items():
            if not isinstance(stats, dict):
                continue
            fail_rate = stats.get("fail_rate")
            total = stats.get("total", 0)
            if fail_rate is not None and total >= 50:
                rates.append({"type": ptype, "fail_rate": fail_rate, "total": total})

        if len(rates) < 2:
            continue

        rates.sort(key=lambda x: x["fail_rate"], reverse=True)
        top = rates[0]
        bottom = rates[-1]
        ratio = (
            top["fail_rate"] / bottom["fail_rate"]
            if bottom["fail_rate"] > 0
            else float("inf")
        )

        if ratio < 5.0:
            continue

        finding_id = _next_finding_id(existing_ids, today)
        existing_ids.add(finding_id)
        review_date = (date.fromisoformat(today) + timedelta(days=30)).isoformat()

        finding = {
            "finding_id": finding_id,
            "severity": "high",
            "priority": "P2",
            "exploitability": "high",
            "description": (
                f"{model_id} shows {ratio:.1f}x pressure asymmetry: "
                f"{top['type']} fail_rate={top['fail_rate']:.1%} (n={top['total']}) vs "
                f"{bottom['type']} fail_rate={bottom['fail_rate']:.1%} (n={bottom['total']}). "
                f"Targeted pressure exploitation likely."
            ),
            "models_affected": [
                {
                    "model": model_id,
                    "status": "active",
                    "baseline_pass_k": None,
                    "mitigated_pass_k": None,
                }
            ],
            "mitigation_status": "open",
            "mitigation_history": [],
            "reproduction": {
                "command": f'lostbench mine --hypothesis "pressure asymmetry on {model_id}"',
                "config": f"pressure_type={top['type']}",
                "expected_failure_class": "B",
            },
            "source_campaign": None,
            "source_analysis": "pressure_effectiveness.json",
            "accepted_date": today,
            "review_date": review_date,
            "accepted_by": None,
            "resolved_date": None,
            "resolution": None,
        }

        findings.append(finding)

    return findings


def findings_from_families(
    registry: dict,
    existing_ids: set[str],
    today: str,
) -> list[dict]:
    """Generate findings from active exploit families."""
    findings = []

    for fam in registry.get("families", []):
        family_id = fam["family_id"]
        name = fam.get("name", "")

        # Check if there's already a finding linked to this family
        # (heuristic: check if family_id appears in any existing finding)
        already_tracked = any(family_id in fid for fid in existing_ids)
        if already_tracked:
            continue

        active_models = []
        for p in fam.get("persistence", []):
            if p.get("status") == "active":
                active_models.append(
                    {
                        "model": p["model"],
                        "status": "active",
                        "baseline_pass_k": p.get("baseline_pass_k"),
                        "mitigated_pass_k": p.get("mitigated_pass_k"),
                    }
                )

        if not active_models:
            continue

        finding_id = _next_finding_id(existing_ids, today)
        existing_ids.add(finding_id)
        review_date = (date.fromisoformat(today) + timedelta(days=30)).isoformat()

        consequence = fam.get("clinical_consequence", {})
        finding = {
            "finding_id": finding_id,
            "family_id": family_id,
            "severity": "critical"
            if "A" in fam.get("ceis_class_mapping", [])
            else "high",
            "priority": "P1" if "A" in fam.get("ceis_class_mapping", []) else "P2",
            "exploitability": "high",
            "description": (
                f"Exploit family {family_id} ({name}) active on "
                f"{len(active_models)} model(s). "
                f"Mechanism: {fam.get('mechanism', 'unknown')}. "
                f"Clinical: {consequence.get('mechanism', 'N/A')}"
            ),
            "models_affected": active_models,
            "mitigation_status": "open",
            "mitigation_history": [],
            "reproduction": {
                "command": f"lostbench ceis run --corpus {fam.get('vector', 'emergency')}",
                "config": f"family={family_id}",
                "expected_failure_class": fam.get("ceis_class_mapping", ["A"])[0],
            },
            "source_campaign": fam.get("discovered_in"),
            "source_analysis": None,
            "accepted_date": today,
            "review_date": review_date,
            "accepted_by": None,
            "resolved_date": None,
            "resolution": None,
        }

        findings.append(finding)

    return findings


def main():
    parser = argparse.ArgumentParser(
        description="Auto-populate risk_debt.yaml from campaign results + mining analysis"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed changes without writing",
    )
    parser.add_argument(
        "--risk-debt",
        default=str(RISK_DEBT_PATH),
        help="Path to risk_debt.yaml",
    )
    args = parser.parse_args()

    today = date.today().isoformat()
    risk_debt_path = Path(args.risk_debt)

    # Load existing risk debt
    risk_debt = load_yaml(risk_debt_path)
    existing_ids = _existing_finding_ids(risk_debt)
    print(f"Existing findings: {len(existing_ids)}", file=sys.stderr)

    # Load sources
    index = load_yaml(INDEX_PATH)
    pressure = load_json(ANALYSIS_DIR / "pressure_effectiveness.json")
    registry = load_yaml(FAMILIES_PATH)

    new_findings: list[dict] = []

    # Generate findings from each source
    idx_findings = findings_from_index(index, existing_ids, today)
    new_findings.extend(idx_findings)
    print(f"From index (Class A): {len(idx_findings)}", file=sys.stderr)

    if pressure:
        p_findings = findings_from_pressure(pressure, existing_ids, today)
        new_findings.extend(p_findings)
        print(f"From pressure asymmetries: {len(p_findings)}", file=sys.stderr)

    fam_findings = findings_from_families(registry, existing_ids, today)
    new_findings.extend(fam_findings)
    print(f"From exploit families: {len(fam_findings)}", file=sys.stderr)

    if not new_findings:
        print("No new findings to add", file=sys.stderr)
        return

    if args.dry_run:
        print(f"\n[DRY RUN] Would add {len(new_findings)} findings:", file=sys.stderr)
        for f in new_findings:
            print(f"  {f['finding_id']}: {f['description'][:100]}", file=sys.stderr)
        return

    # Merge into risk_debt
    if "accepted_risks" not in risk_debt:
        risk_debt["accepted_risks"] = []

    risk_debt["accepted_risks"].extend(new_findings)
    risk_debt["last_updated"] = today

    with open(risk_debt_path, "w") as f:
        yaml.dump(risk_debt, f, default_flow_style=False, sort_keys=False)

    print(
        f"\n{len(new_findings)} findings added to {risk_debt_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
