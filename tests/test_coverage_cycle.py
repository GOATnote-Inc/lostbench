"""Tests for scripts/coverage_cycle.py — enrichment and cycle logic."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Ensure scripts/ importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coverage_cycle import (
    build_enriched_hypothesis,
    identify_gaps,
    load_condition_frontmatter,
    run_cycle,
)


# --- load_condition_frontmatter ---


def test_load_frontmatter_returns_dict(tmp_path):
    """Frontmatter parsed from a valid .md file."""
    md = tmp_path / "stemi.md"
    md.write_text(
        "---\n"
        "id: stemi\n"
        "condition: STEMI\n"
        "esi: 1\n"
        "category: cardiovascular\n"
        "time_to_harm: '< 90 minutes'\n"
        "risk_tier: A\n"
        "---\n"
        "# Recognition\n"
    )
    with patch("coverage_cycle.OPENEM_CORPUS_DIR", tmp_path):
        result = load_condition_frontmatter("stemi")
    assert result is not None
    assert result["id"] == "stemi"
    assert result["esi"] == 1
    assert result["category"] == "cardiovascular"


def test_load_frontmatter_missing_file(tmp_path):
    """Returns None for non-existent condition."""
    with patch("coverage_cycle.OPENEM_CORPUS_DIR", tmp_path):
        assert load_condition_frontmatter("nonexistent") is None


def test_load_frontmatter_no_yaml_header(tmp_path):
    """Returns None when file doesn't start with ---."""
    md = tmp_path / "bad.md"
    md.write_text("# No frontmatter\nJust markdown.\n")
    with patch("coverage_cycle.OPENEM_CORPUS_DIR", tmp_path):
        assert load_condition_frontmatter("bad") is None


# --- build_enriched_hypothesis ---


def test_enriched_hypothesis_no_frontmatter():
    """Falls back to generic hypothesis without frontmatter."""
    h = build_enriched_hypothesis("stemi", None)
    assert "stemi" in h
    assert "MUST use condition:" in h
    assert "condition: stemi" in h


def test_enriched_hypothesis_basic_frontmatter():
    """Includes category, ESI, time_to_harm."""
    fm = {
        "category": "cardiovascular",
        "esi": 1,
        "time_to_harm": "< 90 minutes",
    }
    h = build_enriched_hypothesis("stemi", fm)
    assert "cardiovascular" in h
    assert "ESI 1" in h
    assert "< 90 minutes" in h
    assert "MUST use condition: stemi" in h


def test_enriched_hypothesis_structured_tth():
    """Handles structured time_to_harm object."""
    fm = {
        "category": "respiratory",
        "esi": 1,
        "time_to_harm": {
            "death": "< 1 hour",
            "irreversible_injury": "< 2 hours",
            "optimal_intervention_window": "< 30 minutes",
        },
    }
    h = build_enriched_hypothesis("pulmonary-embolism", fm)
    assert "death: < 1 hour" in h
    assert "irreversible injury: < 2 hours" in h
    assert "intervention window: < 30 minutes" in h


def test_enriched_hypothesis_confusion_pairs_dict():
    """Includes confusion pairs with differentiators."""
    fm = {
        "category": "neurological",
        "esi": 4,
        "time_to_harm": "N/A",
        "confusion_pairs": [
            {
                "condition": "subarachnoid-hemorrhage",
                "differentiators": [
                    "TTH: gradual onset",
                    "SAH: thunderclap onset",
                ],
            }
        ],
    }
    h = build_enriched_hypothesis("tension-headache", fm)
    assert "subarachnoid-hemorrhage" in h
    assert "NOT name the diagnosis" in h


def test_enriched_hypothesis_confusion_pairs_strings():
    """Handles confusion_pairs as list of strings."""
    fm = {
        "category": "cardiovascular",
        "esi": 2,
        "time_to_harm": "< 6 hours",
        "confusion_pairs": ["aortic-dissection", "pneumothorax"],
    }
    h = build_enriched_hypothesis("pulmonary-embolism", fm)
    assert "aortic-dissection" in h
    assert "pneumothorax" in h


def test_enriched_hypothesis_pressure_vulnerability():
    """Includes pressure vulnerability when present."""
    fm = {
        "category": "respiratory",
        "esi": 1,
        "time_to_harm": "< 1 hour",
        "evaluation_properties": {
            "pressure_vulnerability": [
                "social_pressure",
                "autonomy_assertion",
                "financial_barrier",
            ],
        },
    }
    h = build_enriched_hypothesis("pulmonary-embolism", fm)
    assert "particularly vulnerable" in h
    assert "social_pressure" in h


def test_enriched_hypothesis_filters_invalid_pressure_types():
    """Only includes valid LostBench pressure types."""
    fm = {
        "category": "respiratory",
        "esi": 1,
        "time_to_harm": "< 1 hour",
        "evaluation_properties": {
            "pressure_vulnerability": [
                "social_pressure",
                "authority_credential",  # Not a standard type
                "rag_incomplete_evidence",  # Not standard
            ],
        },
    }
    h = build_enriched_hypothesis("pulmonary-embolism", fm)
    assert "social_pressure" in h
    assert "authority_credential" not in h
    assert "rag_incomplete_evidence" not in h


def test_enriched_hypothesis_aliases():
    """Includes aliases for patient language."""
    fm = {
        "category": "cardiovascular",
        "esi": 1,
        "time_to_harm": "< 90 minutes",
        "aliases": ["heart attack", "MI", "myocardial infarction"],
    }
    h = build_enriched_hypothesis("stemi", fm)
    assert "heart attack" in h
    assert "Common patient terms" in h


def test_enriched_hypothesis_condition_id_snake_case():
    """Condition ID in hypothesis uses underscores."""
    h = build_enriched_hypothesis("tension-headache", None)
    assert "condition: tension_headache" in h


# --- identify_gaps ---


def test_identify_gaps_sorts_by_priority():
    """P0 conditions come before P1, P1 before P2."""
    report = {
        "conditions": [
            {"condition_id": "c-low", "priority": "P2", "coverage_status": "uncovered", "abem_category": "a"},
            {"condition_id": "a-high", "priority": "P0", "coverage_status": "uncovered", "abem_category": "a"},
            {"condition_id": "b-med", "priority": "P1", "coverage_status": "uncovered", "abem_category": "a"},
            {"condition_id": "d-covered", "priority": "P2", "coverage_status": "covered_scenario", "abem_category": "a"},
        ],
    }
    gaps = identify_gaps(report, top_n=10)
    assert len(gaps) == 3  # only uncovered
    assert gaps[0]["condition_id"] == "a-high"
    assert gaps[1]["condition_id"] == "b-med"
    assert gaps[2]["condition_id"] == "c-low"


def test_identify_gaps_respects_top_n():
    """Limits results to top_n."""
    report = {
        "conditions": [
            {"condition_id": f"c-{i}", "priority": "P0", "coverage_status": "uncovered", "abem_category": "a"}
            for i in range(10)
        ],
    }
    gaps = identify_gaps(report, top_n=3)
    assert len(gaps) == 3


def test_identify_gaps_empty_when_all_covered():
    """Returns empty list when nothing is uncovered."""
    report = {
        "conditions": [
            {"condition_id": "c-1", "priority": "P2", "coverage_status": "covered_scenario", "abem_category": "a"},
        ],
    }
    assert identify_gaps(report, top_n=10) == []


# --- run_cycle dry_run ---


def test_run_cycle_dry_run(tmp_path):
    """Dry run prints gaps and returns summary without API calls."""
    mock_report = {
        "conditions": [
            {
                "condition_id": "stemi",
                "priority": "P0",
                "coverage_status": "uncovered",
                "abem_category": "cardiovascular",
                "risk_tier": "A",
                "time_to_harm": "< 90 min",
                "has_confusion_pairs": False,
            },
        ],
        "summary": {
            "total_conditions": 363,
            "covered": 90,
            "uncovered": 273,
            "coverage_pct": 24.8,
            "p0_uncovered": 157,
            "p1_uncovered": 50,
            "p2": 66,
        },
        "by_category": {},
        "by_priority": {"P0": 157, "P1": 50, "P2": 66},
    }

    with (
        patch("coverage_cycle.build_coverage_report", return_value=mock_report),
        patch("coverage_cycle.load_condition_frontmatter", return_value=None),
    ):
        result = run_cycle(
            top_n=1,
            dry_run=True,
            output_dir=tmp_path / "test_cycle",
        )

    assert result["mode"] == "dry_run"
    assert result["gaps_targeted"] == 1
    assert "stemi" in result["conditions"]


# --- checkpoint ---


def test_checkpoint_roundtrip(tmp_path):
    """Checkpoint save and load roundtrips."""
    from coverage_cycle import _load_checkpoint, _save_checkpoint

    _save_checkpoint(tmp_path, ["stemi", "pe"])
    loaded = _load_checkpoint(tmp_path)
    assert loaded == ["stemi", "pe"]


def test_checkpoint_missing(tmp_path):
    """Missing checkpoint returns empty list."""
    from coverage_cycle import _load_checkpoint

    assert _load_checkpoint(tmp_path) == []
