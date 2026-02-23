"""Tests for multimodal vector scenarios (MMV-001 through MMV-008)."""

from lostbench.scenarios.loader import load_scenarios
from lostbench.judge import build_judge_system_prompt, VECTOR_PROMPT_MAP


class TestMultimodalScenarioLoading:
    """Verify multimodal scenarios load correctly."""

    def test_loads_all_scenarios(self):
        scenarios = load_scenarios("multimodal")
        assert len(scenarios) == 8

    def test_scenario_ids_sequential(self):
        scenarios = load_scenarios("multimodal")
        ids = {s["id"] for s in scenarios}
        for i in range(1, 9):
            assert f"MMV-{i:03d}" in ids

    def test_required_fields(self):
        scenarios = load_scenarios("multimodal")
        for s in scenarios:
            assert "id" in s
            assert "condition" in s
            assert "initial" in s
            assert "pressure" in s
            assert "ceis" in s

    def test_vector_field(self):
        scenarios = load_scenarios("multimodal")
        for s in scenarios:
            assert s.get("vector") == "multimodal", (
                f"{s['id']} missing vector=multimodal"
            )

    def test_image_blocks_present(self):
        """Multimodal scenarios should have [IMAGE: ...] blocks in pressure turns."""
        scenarios = load_scenarios("multimodal")
        for s in scenarios:
            has_image = False
            for p in s.get("pressure", []):
                if "[IMAGE:" in p.get("content", ""):
                    has_image = True
                    break
            assert has_image, f"{s['id']} missing [IMAGE:] block in pressure turns"

    def test_ceis_metadata(self):
        scenarios = load_scenarios("multimodal")
        for s in scenarios:
            assert s["ceis"]["required_escalation_level"] == 3
            assert s["ceis"]["suite"] == "capability"
            assert 0.0 <= s["ceis"]["severity_weight"] <= 2.0

    def test_reference_responses_present(self):
        scenarios = load_scenarios("multimodal")
        for s in scenarios:
            refs = s.get("reference_responses") or s.get("reference")
            assert refs, f"{s['id']} missing reference responses"

    def test_conditions_filter(self):
        scenarios = load_scenarios("multimodal", conditions=["MMV-001", "MMV-003"])
        assert len(scenarios) == 2
        ids = {s["id"] for s in scenarios}
        assert ids == {"MMV-001", "MMV-003"}


class TestMultimodalJudgeRouting:
    """Verify judge prompt routing for multimodal vector."""

    def test_vector_prompt_mapping_exists(self):
        assert "multimodal" in VECTOR_PROMPT_MAP

    def test_judge_prompt_loads(self):
        scenario = {"vector": "multimodal", "condition": "stemi"}
        prompt = build_judge_system_prompt("unknown", scenario=scenario)
        assert "visual" in prompt.lower() or "image" in prompt.lower()
        assert "maintained" in prompt.lower()
