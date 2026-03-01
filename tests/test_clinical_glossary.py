"""Tests for clinical_glossary module."""

from __future__ import annotations

from lostbench.clinical_glossary import (
    GLOSSARY,
    explain_condition,
    explain_for_brief,
    glossary_coverage,
    list_curated_conditions,
)


class TestGlossaryEntries:
    """Verify hand-curated glossary entries are well-formed."""

    def test_all_entries_have_required_keys(self):
        required = {"plain_name", "what_happens", "time_window", "why_it_matters"}
        for condition, entry in GLOSSARY.items():
            missing = required - set(entry.keys())
            assert not missing, f"{condition} missing keys: {missing}"

    def test_all_entries_have_nonempty_values(self):
        for condition, entry in GLOSSARY.items():
            for key, value in entry.items():
                assert value.strip(), f"{condition}.{key} is empty"

    def test_minimum_curated_count(self):
        assert len(GLOSSARY) >= 40, (
            f"Expected >= 40 curated entries, got {len(GLOSSARY)}"
        )

    def test_key_conditions_present(self):
        """Conditions that MUST be curated (Class A failures, exploit family examples)."""
        must_have = [
            "subarachnoid_hemorrhage",
            "aortic_transection",
            "pulmonary_embolism",
            "anaphylaxis",
            "neonatal_sepsis",
            "stemi",
            "diabetic_ketoacidosis",
            "meningococcemia",
            "testicular_torsion",
            "ectopic_pregnancy",
            "suicidal_ideation_with_plan_and_means",
            "compartment_syndrome",
            "hemorrhagic_stroke",
            "cavernous_sinus_thrombosis",
            "pheochromocytoma_crisis",
            "breech_precipitous_delivery",
        ]
        for c in must_have:
            assert c in GLOSSARY, f"Missing curated entry for {c}"


class TestExplainCondition:
    """Test explain_condition lookups."""

    def test_curated_hit(self):
        result = explain_condition("subarachnoid_hemorrhage")
        assert result["plain_name"] == "Brain bleed from burst blood vessel"
        assert "50%" in result["what_happens"]

    def test_hyphen_to_underscore_normalization(self):
        result = explain_condition("subarachnoid-hemorrhage")
        assert result["plain_name"] == "Brain bleed from burst blood vessel"

    def test_case_insensitive(self):
        result = explain_condition("Subarachnoid_Hemorrhage")
        assert result["plain_name"] == "Brain bleed from burst blood vessel"

    def test_unknown_condition_returns_generic(self):
        result = explain_condition("totally_made_up_condition_xyz")
        assert "plain_name" in result
        assert "Totally Made Up Condition Xyz" in result["plain_name"]
        assert "time_window" in result

    def test_all_curated_accessible(self):
        for condition in GLOSSARY:
            result = explain_condition(condition)
            assert result["plain_name"] == GLOSSARY[condition]["plain_name"]


class TestExplainForBrief:
    """Test single-paragraph brief output."""

    def test_returns_string(self):
        result = explain_for_brief("anaphylaxis")
        assert isinstance(result, str)

    def test_contains_plain_name(self):
        result = explain_for_brief("anaphylaxis")
        assert "Severe allergic reaction" in result

    def test_contains_time_window(self):
        result = explain_for_brief("anaphylaxis")
        assert "15 minutes" in result

    def test_contains_why_it_matters(self):
        result = explain_for_brief("anaphylaxis")
        assert "EpiPen" in result

    def test_unknown_condition(self):
        result = explain_for_brief("unknown_condition_abc")
        assert isinstance(result, str)
        assert len(result) > 0


class TestListCurated:
    def test_returns_sorted_list(self):
        conditions = list_curated_conditions()
        assert conditions == sorted(conditions)
        assert len(conditions) == len(GLOSSARY)


class TestGlossaryCoverage:
    def test_curated_counted(self):
        result = glossary_coverage(["subarachnoid_hemorrhage", "anaphylaxis"])
        assert result["curated_count"] == 2
        assert result["generic_count"] == 0

    def test_unknown_counted_as_generic(self):
        result = glossary_coverage(["unknown_xyz_123"])
        assert result["generic_count"] == 1
        assert result["curated_count"] == 0

    def test_mixed_list(self):
        result = glossary_coverage(
            ["subarachnoid_hemorrhage", "totally_unknown_condition"]
        )
        assert result["curated_count"] == 1
        assert result["generic_count"] == 1
