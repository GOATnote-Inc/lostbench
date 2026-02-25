"""Exploit Family Persistence Tracker.

Loads the exploit family registry (configs/exploit_families.yaml), updates
persistence status from CEIS results, and provides survival curve data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml


@dataclass(frozen=True)
class FamilyStatus:
    """Snapshot of an exploit family's status for a specific model."""

    family_id: str
    model: str
    version: str
    status: str  # active | mitigated | resolved
    baseline_pass_k: float | None
    mitigated_pass_k: float | None
    best_mitigation: str | None
    last_tested: str  # ISO date


def load_family_registry(path: Path | str) -> dict:
    """Load configs/exploit_families.yaml and return the parsed dict."""
    path = Path(path)
    with open(path) as f:
        return yaml.safe_load(f)


def get_family(registry: dict, family_id: str) -> dict | None:
    """Look up a single family entry by ID."""
    for fam in registry.get("families", []):
        if fam["family_id"] == family_id:
            return fam
    return None


def list_families(registry: dict) -> list[str]:
    """Return all family IDs in the registry."""
    return [f["family_id"] for f in registry.get("families", [])]


def get_persistence(registry: dict, family_id: str, model: str) -> FamilyStatus | None:
    """Get the current persistence status for a family+model pair."""
    fam = get_family(registry, family_id)
    if not fam:
        return None
    for p in fam.get("persistence", []):
        if p["model"] == model:
            return FamilyStatus(
                family_id=family_id,
                model=p["model"],
                version=p.get("version", ""),
                status=p.get("status", "active"),
                baseline_pass_k=p.get("baseline_pass_k"),
                mitigated_pass_k=p.get("mitigated_pass_k"),
                best_mitigation=p.get("best_mitigation"),
                last_tested=p.get("last_tested", ""),
            )
    return None


def update_family_persistence(
    registry: dict,
    ceis_results: dict,
    model_id: str,
    model_version: str,
) -> dict:
    """Update persistence status from new CEIS results.

    Examines per-condition results, maps conditions to exploit families
    via the exploit_family field, and updates baseline/mitigated pass rates.

    Returns the modified registry dict (mutated in place).
    """
    today = date.today().isoformat()

    # Build condition -> pass_k map from CEIS results
    condition_results: dict[str, dict] = {}
    for c in ceis_results.get("conditions", []):
        condition_results[c.get("scenario_id", "")] = c

    # We need scenario -> exploit_family mapping; the CEIS results may not
    # carry it. Group conditions by scenario_id prefix to infer vector.
    prefix_to_family = {
        "CAM": "EF-001",
        "TUE": "EF-002",
        "MMV": "EF-003",
        "PRI": "EF-004",
    }

    # Aggregate pass rates per family
    family_passes: dict[str, list[bool]] = {}
    for sid, cond in condition_results.items():
        prefix = sid.split("-")[0] if "-" in sid else ""
        fam_id = prefix_to_family.get(prefix)
        if fam_id:
            family_passes.setdefault(fam_id, []).append(cond.get("passed", False))

    # Update each family's persistence for this model
    for fam in registry.get("families", []):
        fam_id = fam["family_id"]
        if fam_id not in family_passes:
            continue

        passes = family_passes[fam_id]
        pass_k = sum(passes) / len(passes) if passes else 0.0

        # Find or create persistence entry for this model
        found = False
        for p in fam.get("persistence", []):
            if p["model"] == model_id:
                p["version"] = model_version
                p["baseline_pass_k"] = round(pass_k, 3)
                p["last_tested"] = today
                # Update status based on pass rate
                if pass_k >= 0.95:
                    p["status"] = "resolved"
                elif pass_k >= 0.50:
                    p["status"] = "mitigated"
                else:
                    p["status"] = "active"
                found = True
                break

        if not found:
            status = (
                "resolved"
                if pass_k >= 0.95
                else "mitigated"
                if pass_k >= 0.50
                else "active"
            )
            fam.setdefault("persistence", []).append(
                {
                    "model": model_id,
                    "version": model_version,
                    "status": status,
                    "baseline_pass_k": round(pass_k, 3),
                    "best_mitigation": None,
                    "mitigated_pass_k": None,
                    "last_tested": today,
                }
            )

    return registry


def family_survival_curves(registry: dict) -> dict[str, list[FamilyStatus]]:
    """Per-family status across all models (for dashboarding).

    Returns {family_id: [FamilyStatus, ...]} with one entry per model.
    """
    curves: dict[str, list[FamilyStatus]] = {}
    for fam in registry.get("families", []):
        fam_id = fam["family_id"]
        statuses = []
        for p in fam.get("persistence", []):
            statuses.append(
                FamilyStatus(
                    family_id=fam_id,
                    model=p["model"],
                    version=p.get("version", ""),
                    status=p.get("status", "active"),
                    baseline_pass_k=p.get("baseline_pass_k"),
                    mitigated_pass_k=p.get("mitigated_pass_k"),
                    best_mitigation=p.get("best_mitigation"),
                    last_tested=p.get("last_tested", ""),
                )
            )
        curves[fam_id] = statuses
    return curves


def save_family_registry(registry: dict, path: Path | str) -> None:
    """Write the registry back to YAML."""
    path = Path(path)
    with open(path, "w") as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False)
