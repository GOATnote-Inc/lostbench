"""Tests for reference solution validation.

Verifies that each scenario's reference responses are structurally valid.
Full grading validation (feeding references through the judge pipeline)
requires API keys and is tested separately.
"""

import pytest

from lostbench.scenarios.loader import load_scenarios


EXPANSION_CORPORA = ["tool-use", "code-agent", "multimodal", "integrated"]


class TestReferenceSolutionStructure:
    """Verify all expansion scenarios have valid reference solution structure."""

    @pytest.mark.parametrize("corpus", EXPANSION_CORPORA)
    def test_all_scenarios_have_references(self, corpus):
        scenarios = load_scenarios(corpus)
        for s in scenarios:
            refs = s.get("reference_responses") or s.get("reference")
            assert refs, f"{s['id']} in {corpus} missing reference responses"
            assert isinstance(refs, list), (
                f"{s['id']} reference must be a list, got {type(refs).__name__}"
            )
            assert len(refs) >= 2, (
                f"{s['id']} should have at least 2 reference responses"
            )

    @pytest.mark.parametrize("corpus", EXPANSION_CORPORA)
    def test_reference_responses_have_content(self, corpus):
        scenarios = load_scenarios(corpus)
        for s in scenarios:
            refs = s.get("reference_responses") or s.get("reference")
            if not refs:
                continue
            for i, ref in enumerate(refs):
                if isinstance(ref, dict):
                    # May have turn/response or turn/content structure
                    response = ref.get("response") or ref.get("content", "")
                else:
                    response = str(ref)
                assert len(response) > 20, (
                    f"{s['id']} reference[{i}] too short: {response[:50]}"
                )

    @pytest.mark.parametrize("corpus", EXPANSION_CORPORA)
    def test_reference_count_matches_turns(self, corpus):
        """Reference count should cover initial + at least one pressure turn."""
        scenarios = load_scenarios(corpus)
        for s in scenarios:
            refs = s.get("reference_responses") or s.get("reference")
            if not refs:
                continue
            n_turns = 1 + len(s.get("pressure", []))
            # At least 2 references (initial + one pressure), but don't require all
            assert len(refs) >= 2, (
                f"{s['id']} has {n_turns} turns but only {len(refs)} references"
            )


class TestAdversarialAllReferences:
    """Verify adversarial-all corpus loads all expansion scenarios."""

    def test_adversarial_all_includes_expansion(self):
        all_scenarios = load_scenarios("adversarial-all")
        ids = {s["id"] for s in all_scenarios}
        # Should include at least one from each new category
        assert any(sid.startswith("TUE-") for sid in ids)
        assert any(sid.startswith("CAM-") for sid in ids)
        assert any(sid.startswith("MMV-") for sid in ids)
        assert any(sid.startswith("PRI-") for sid in ids)
        # Plus original adversarial
        assert any(sid.startswith("ADV-") for sid in ids)

    def test_adversarial_all_total_count(self):
        all_scenarios = load_scenarios("adversarial-all")
        # 10 ADV + 8 TUE + 8 CAM + 8 MMV + 9 PRI = 43
        assert len(all_scenarios) == 43
