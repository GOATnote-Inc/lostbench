"""Tests for tool-use exploit chain scenarios (TUE-001 through TUE-008)."""

from lostbench.scenarios.loader import load_scenarios
from lostbench.judge import build_judge_system_prompt, VECTOR_PROMPT_MAP


class TestToolUseScenarioLoading:
    """Verify tool-use scenarios load correctly."""

    def test_loads_all_scenarios(self):
        scenarios = load_scenarios("tool-use")
        assert len(scenarios) == 8

    def test_scenario_ids_sequential(self):
        scenarios = load_scenarios("tool-use")
        ids = {s["id"] for s in scenarios}
        for i in range(1, 9):
            assert f"TUE-{i:03d}" in ids

    def test_required_fields(self):
        scenarios = load_scenarios("tool-use")
        for s in scenarios:
            assert "id" in s
            assert "condition" in s
            assert "initial" in s
            assert "pressure" in s
            assert "ceis" in s

    def test_vector_field(self):
        scenarios = load_scenarios("tool-use")
        for s in scenarios:
            assert s.get("vector") == "tool_use", f"{s['id']} missing vector=tool_use"

    def test_system_context_present(self):
        scenarios = load_scenarios("tool-use")
        for s in scenarios:
            assert "system_context" in s, f"{s['id']} missing system_context"
            assert len(s["system_context"]) > 50, f"{s['id']} system_context too short"

    def test_injected_context_on_pressure_turns(self):
        """At least some pressure turns should have injected_context."""
        scenarios = load_scenarios("tool-use")
        total_injected = 0
        for s in scenarios:
            for p in s.get("pressure", []):
                if p.get("injected_context"):
                    total_injected += 1
        assert total_injected >= 8, "Expected at least 8 turns with injected_context"

    def test_ceis_metadata(self):
        scenarios = load_scenarios("tool-use")
        for s in scenarios:
            assert s["ceis"]["required_escalation_level"] == 3
            assert s["ceis"]["suite"] == "capability"
            assert 0.0 <= s["ceis"]["severity_weight"] <= 2.0

    def test_reference_responses_present(self):
        scenarios = load_scenarios("tool-use")
        for s in scenarios:
            refs = s.get("reference_responses") or s.get("reference")
            assert refs, f"{s['id']} missing reference responses"

    def test_conditions_filter(self):
        scenarios = load_scenarios("tool-use", conditions=["TUE-001", "TUE-003"])
        assert len(scenarios) == 2
        ids = {s["id"] for s in scenarios}
        assert ids == {"TUE-001", "TUE-003"}


class TestToolUseJudgeRouting:
    """Verify judge prompt routing for tool-use vector."""

    def test_vector_prompt_mapping_exists(self):
        assert "tool_use" in VECTOR_PROMPT_MAP

    def test_judge_prompt_loads(self):
        scenario = {"vector": "tool_use", "condition": "stemi"}
        prompt = build_judge_system_prompt("unknown", scenario=scenario)
        assert "tool" in prompt.lower()
        assert "maintained" in prompt.lower()
