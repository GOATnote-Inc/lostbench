"""Program Self-Audit.

Blind spot detection, calibration drift monitoring, and program health checks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class CoverageBlindSpot:
    """A region of the taxonomy with insufficient coverage."""

    vector: str
    condition: str | None
    issue: str
    severity: str  # critical | warning | info


@dataclass
class CalibrationMetric:
    """Layer 0 vs Layer 2 agreement for a single result set."""

    source: str
    layer_0_pct: float
    layer_2_pct: float
    total_turns: int


@dataclass
class RiskDebtItem:
    """A single risk debt entry."""

    finding_id: str
    family_id: str
    severity: str
    review_date: str
    is_overdue: bool


@dataclass
class AuditReport:
    """Complete audit report."""

    blind_spots: list[CoverageBlindSpot] = field(default_factory=list)
    calibration_metrics: list[CalibrationMetric] = field(default_factory=list)
    risk_debt_items: list[RiskDebtItem] = field(default_factory=list)
    overdue_risk_count: int = 0
    total_families: int = 0
    active_families: int = 0
    coverage_pct: float = 0.0

    def to_text(self) -> str:
        """Generate text report."""
        lines = [
            "=" * 60,
            "ADVERSARIAL PROGRAM SELF-AUDIT",
            "=" * 60,
            "",
            f"Exploit Families: {self.active_families} active / {self.total_families} total",
            f"Coverage: {self.coverage_pct:.1f}%",
            f"Overdue Risk Debt: {self.overdue_risk_count}",
            "",
        ]

        if self.blind_spots:
            lines.append("BLIND SPOTS:")
            for bs in self.blind_spots:
                lines.append(f"  [{bs.severity}] {bs.vector}: {bs.issue}")
            lines.append("")

        if self.calibration_metrics:
            lines.append("CALIBRATION:")
            for cm in self.calibration_metrics:
                lines.append(
                    f"  {cm.source}: Layer 0 {cm.layer_0_pct:.1f}%, "
                    f"Layer 2 {cm.layer_2_pct:.1f}% ({cm.total_turns} turns)"
                )
            lines.append("")

        if self.risk_debt_items:
            lines.append("RISK DEBT:")
            for rd in self.risk_debt_items:
                status = "OVERDUE" if rd.is_overdue else "active"
                lines.append(
                    f"  {rd.finding_id} ({rd.family_id}): "
                    f"{rd.severity}, review by {rd.review_date} [{status}]"
                )
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


def blind_spot_detection(
    taxonomy_path: Path | str,
    scenarios_dir: Path | str,
    results_dir: Path | str,
) -> list[CoverageBlindSpot]:
    """Identify taxonomy regions with zero or insufficient coverage."""
    taxonomy_path = Path(taxonomy_path)
    scenarios_dir = Path(scenarios_dir)
    results_dir = Path(results_dir)

    with open(taxonomy_path) as f:
        taxonomy = yaml.safe_load(f)

    spots: list[CoverageBlindSpot] = []

    for vec in taxonomy.get("vectors", []):
        vid = vec["id"]
        corpus_dir_name = Path(vec.get("corpus_dir", "")).name
        corpus_dir = scenarios_dir / corpus_dir_name
        conditions = vec.get("conditions_targeted", [])

        if not corpus_dir.exists():
            spots.append(
                CoverageBlindSpot(
                    vector=vid,
                    condition=None,
                    issue=f"Scenario directory does not exist: {corpus_dir}",
                    severity="critical",
                )
            )
            continue

        scenario_files = list(corpus_dir.glob("*.yaml"))
        scenario_conditions: set[str] = set()
        for sf in scenario_files:
            try:
                with open(sf) as f:
                    s = yaml.safe_load(f)
                if s and "condition" in s:
                    scenario_conditions.add(s["condition"])
            except Exception:
                continue

        for cond in conditions:
            if cond not in scenario_conditions:
                spots.append(
                    CoverageBlindSpot(
                        vector=vid,
                        condition=cond,
                        issue=f"No scenario for {cond} under {vid}",
                        severity="warning",
                    )
                )

    # Check for vectors with no results
    index_path = results_dir / "index.yaml"
    if index_path.exists():
        with open(index_path) as f:
            index = yaml.safe_load(f) or {}
        tested_corpora = set()
        for exp in index.get("experiments", []):
            corpus = exp.get("corpus", exp.get("experiment", ""))
            tested_corpora.add(corpus)

        for vec in taxonomy.get("vectors", []):
            vid = vec["id"]
            if vid not in tested_corpora:
                spots.append(
                    CoverageBlindSpot(
                        vector=vid,
                        condition=None,
                        issue=f"Vector {vid} has no evaluation results",
                        severity="critical",
                    )
                )

    return spots


def calibration_drift_check(
    results_dir: Path | str,
) -> list[CalibrationMetric]:
    """Check Layer 0 vs Layer 2 agreement rates across CEIS results."""
    results_dir = Path(results_dir)
    metrics: list[CalibrationMetric] = []

    for p in sorted(results_dir.rglob("ceis_results.json")):
        try:
            with open(p) as f:
                data = json.load(f)
            gm = data.get("grading_metadata", {})
            total = gm.get("total_turns_graded", 0)
            if total == 0:
                continue
            l0_pct = gm.get("layer_0_pct", 0.0)
            l2_pct = gm.get("layer_2_pct", 0.0)
            metrics.append(
                CalibrationMetric(
                    source=str(p.relative_to(results_dir)),
                    layer_0_pct=l0_pct,
                    layer_2_pct=l2_pct,
                    total_turns=total,
                )
            )
        except (json.JSONDecodeError, OSError):
            continue

    return metrics


def check_risk_debt(
    risk_debt_path: Path | str,
    today: str | None = None,
) -> list[RiskDebtItem]:
    """Check risk debt register for overdue items."""
    risk_debt_path = Path(risk_debt_path)
    if not risk_debt_path.exists():
        return []

    from datetime import date as date_type

    if today is None:
        today = date_type.today().isoformat()

    with open(risk_debt_path) as f:
        data = yaml.safe_load(f) or {}

    items: list[RiskDebtItem] = []
    for risk in data.get("accepted_risks", []):
        if risk.get("resolved_date"):
            continue  # Already resolved
        review_date = risk.get("review_date", "")
        is_overdue = review_date < today if review_date else True
        items.append(
            RiskDebtItem(
                finding_id=risk.get("finding_id", "unknown"),
                family_id=risk.get("family_id", "unknown"),
                severity=risk.get("severity", "unknown"),
                review_date=review_date,
                is_overdue=is_overdue,
            )
        )

    return items


def run_audit(
    taxonomy_path: Path | str,
    scenarios_dir: Path | str,
    results_dir: Path | str,
    family_registry_path: Path | str | None = None,
    risk_debt_path: Path | str | None = None,
) -> AuditReport:
    """Run the full program self-audit."""
    blind_spots = blind_spot_detection(taxonomy_path, scenarios_dir, results_dir)

    calibration = calibration_drift_check(results_dir)

    risk_debt: list[RiskDebtItem] = []
    if risk_debt_path:
        risk_debt = check_risk_debt(risk_debt_path)
    overdue = sum(1 for r in risk_debt if r.is_overdue)

    # Family stats
    total_families = 0
    active_families = 0
    if family_registry_path:
        frp = Path(family_registry_path)
        if frp.exists():
            with open(frp) as f:
                registry = yaml.safe_load(f) or {}
            families = registry.get("families", [])
            total_families = len(families)
            for fam in families:
                for p in fam.get("persistence", []):
                    if p.get("status") == "active":
                        active_families += 1
                        break

    # Coverage percentage
    total_cells = 0
    covered_cells = 0
    taxonomy_path = Path(taxonomy_path)
    if taxonomy_path.exists():
        with open(taxonomy_path) as f:
            taxonomy = yaml.safe_load(f) or {}
        for vec in taxonomy.get("vectors", []):
            conditions = vec.get("conditions_targeted", [])
            total_cells += len(conditions)
            # Check how many have scenarios
            scenarios_dir_p = Path(scenarios_dir)
            corpus_dir = scenarios_dir_p / Path(vec.get("corpus_dir", "")).name
            if corpus_dir.exists():
                for sf in corpus_dir.glob("*.yaml"):
                    try:
                        with open(sf) as f:
                            s = yaml.safe_load(f)
                        if s and s.get("condition") in conditions:
                            covered_cells += 1
                    except Exception:
                        continue

    coverage_pct = (covered_cells / total_cells * 100) if total_cells > 0 else 0.0

    return AuditReport(
        blind_spots=blind_spots,
        calibration_metrics=calibration,
        risk_debt_items=risk_debt,
        overdue_risk_count=overdue,
        total_families=total_families,
        active_families=active_families,
        coverage_pct=coverage_pct,
    )
