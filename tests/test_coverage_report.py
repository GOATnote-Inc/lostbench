"""Tests for scripts/coverage_report.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from coverage_report import (
    _assign_priority,
    _load_covered_conditions,
    build_coverage_report,
    format_summary,
    format_text,
)


class TestAssignPriority:
    def test_uncovered_tier_a_is_p0(self):
        cond = {"risk_tier": "A"}
        assert _assign_priority(cond, "uncovered") == "P0"

    def test_uncovered_tier_b_is_p1(self):
        cond = {"risk_tier": "B"}
        assert _assign_priority(cond, "uncovered") == "P1"

    def test_uncovered_tier_c_is_p2(self):
        cond = {"risk_tier": "C"}
        assert _assign_priority(cond, "uncovered") == "P2"

    def test_covered_is_p2(self):
        cond = {"risk_tier": "A"}
        assert _assign_priority(cond, "covered_scenario") == "P2"


class TestBuildCoverageReport:
    def test_basic_report_structure(self):
        """Test with mock conditions — no OpenEM dependency."""
        mock_conditions = [
            {
                "condition_id": "stemi",
                "abem_category": "cardiovascular",
                "risk_tier": "A",
                "time_to_harm": "1-2 hours",
            },
            {
                "condition_id": "fake_condition_xyz",
                "abem_category": "neurological",
                "risk_tier": "A",
                "time_to_harm": "minutes",
            },
            {
                "condition_id": "another_fake",
                "abem_category": "respiratory",
                "risk_tier": "B",
                "time_to_harm": "2-4 hours",
            },
        ]

        report = build_coverage_report(openem_conditions=mock_conditions)

        assert "conditions" in report
        assert "summary" in report
        assert "by_category" in report
        assert "by_priority" in report
        assert len(report["conditions"]) == 3
        assert report["summary"]["total_conditions"] == 3

    def test_covered_condition_detected(self):
        """stemi should be covered (exists in tier1 scenarios)."""
        mock_conditions = [
            {
                "condition_id": "stemi",
                "abem_category": "cardiovascular",
                "risk_tier": "A",
                "time_to_harm": "1-2 hours",
            },
        ]

        report = build_coverage_report(openem_conditions=mock_conditions)
        stemi = report["conditions"][0]
        # stemi is a scenario in tier1, so it should be covered
        assert stemi["coverage_status"] in ("covered_scenario", "covered_seed")

    def test_uncovered_condition_detected(self):
        """A fake condition should be uncovered."""
        mock_conditions = [
            {
                "condition_id": "totally_fake_condition",
                "abem_category": "neurological",
                "risk_tier": "A",
                "time_to_harm": "minutes",
            },
        ]

        report = build_coverage_report(openem_conditions=mock_conditions)
        assert report["conditions"][0]["coverage_status"] == "uncovered"
        assert report["conditions"][0]["priority"] == "P0"

    def test_category_grouping(self):
        """Categories should be properly grouped."""
        mock_conditions = [
            {"condition_id": "c1", "abem_category": "cardiovascular", "risk_tier": "A"},
            {"condition_id": "c2", "abem_category": "cardiovascular", "risk_tier": "B"},
            {"condition_id": "c3", "abem_category": "neurological", "risk_tier": "A"},
        ]

        report = build_coverage_report(openem_conditions=mock_conditions)
        assert "cardiovascular" in report["by_category"]
        assert "neurological" in report["by_category"]
        assert report["by_category"]["cardiovascular"]["total"] == 2

    def test_confusion_pairs_flag(self):
        """Conditions with confusion_pairs should be flagged."""
        mock_conditions = [
            {
                "condition_id": "tension_headache",
                "abem_category": "neurological",
                "risk_tier": "B",
                "confusion_pairs": [{"condition": "subarachnoid_hemorrhage", "type": "CRITICAL_BOUNDARY"}],
            },
        ]

        report = build_coverage_report(openem_conditions=mock_conditions)
        assert report["conditions"][0]["has_confusion_pairs"] is True


class TestFormatOutput:
    def test_format_text_has_header(self):
        report = build_coverage_report(openem_conditions=[
            {"condition_id": "test", "abem_category": "cardiovascular", "risk_tier": "A"},
        ])
        text = format_text(report)
        assert "LOSTBENCH COVERAGE REPORT" in text
        assert "Coverage:" in text

    def test_format_summary_one_liner(self):
        report = build_coverage_report(openem_conditions=[
            {"condition_id": "test", "abem_category": "cardiovascular", "risk_tier": "A"},
        ])
        summary = format_summary(report)
        assert "Coverage:" in summary
        assert "P0 uncovered:" in summary

    def test_json_roundtrip(self):
        report = build_coverage_report(openem_conditions=[
            {"condition_id": "test", "abem_category": "cardiovascular", "risk_tier": "A"},
        ])
        json_str = json.dumps(report)
        parsed = json.loads(json_str)
        assert parsed["summary"]["total_conditions"] == 1


class TestLoadCoveredConditions:
    def test_loads_from_tier1(self):
        """Should find at least some conditions from tier1 scenarios."""
        covered = _load_covered_conditions()
        # We know tier1 has 78 scenarios with various conditions
        assert len(covered) > 0

    def test_stemi_is_covered(self):
        """stemi should be found in tier1 or seeds."""
        covered = _load_covered_conditions()
        assert "stemi" in covered
