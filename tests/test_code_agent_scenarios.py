"""Tests for code-agent misuse scenarios (CAM-001 through CAM-008)."""

from lostbench.scenarios.loader import load_scenarios
from lostbench.judge import build_judge_system_prompt, VECTOR_PROMPT_MAP


class TestCodeAgentScenarioLoading:
    """Verify code-agent scenarios load correctly."""

    def test_loads_all_scenarios(self):
        scenarios = load_scenarios("code-agent")
        assert len(scenarios) == 8

    def test_scenario_ids_sequential(self):
        scenarios = load_scenarios("code-agent")
        ids = {s["id"] for s in scenarios}
        for i in range(1, 9):
            assert f"CAM-{i:03d}" in ids

    def test_required_fields(self):
        scenarios = load_scenarios("code-agent")
        for s in scenarios:
            assert "id" in s
            assert "condition" in s
            assert "initial" in s
            assert "pressure" in s
            assert "ceis" in s

    def test_vector_field(self):
        scenarios = load_scenarios("code-agent")
        for s in scenarios:
            assert s.get("vector") == "code_agent", (
                f"{s['id']} missing vector=code_agent"
            )

    def test_system_context_or_code_context(self):
        """Each code-agent scenario should have system_context and/or code_context."""
        scenarios = load_scenarios("code-agent")
        for s in scenarios:
            has_ctx = bool(s.get("system_context")) or bool(s.get("code_context"))
            assert has_ctx, f"{s['id']} missing system_context or code_context"

    def test_ceis_metadata(self):
        scenarios = load_scenarios("code-agent")
        for s in scenarios:
            assert s["ceis"]["required_escalation_level"] == 3
            assert s["ceis"]["suite"] == "capability"
            assert 0.0 <= s["ceis"]["severity_weight"] <= 2.0

    def test_reference_responses_present(self):
        scenarios = load_scenarios("code-agent")
        for s in scenarios:
            refs = s.get("reference_responses") or s.get("reference")
            assert refs, f"{s['id']} missing reference responses"

    def test_conditions_filter(self):
        scenarios = load_scenarios("code-agent", conditions=["CAM-001", "CAM-005"])
        assert len(scenarios) == 2
        ids = {s["id"] for s in scenarios}
        assert ids == {"CAM-001", "CAM-005"}


class TestCodeAgentJudgeRouting:
    """Verify judge prompt routing for code-agent vector."""

    def test_vector_prompt_mapping_exists(self):
        assert "code_agent" in VECTOR_PROMPT_MAP

    def test_judge_prompt_loads(self):
        scenario = {"vector": "code_agent", "condition": "stemi"}
        prompt = build_judge_system_prompt("unknown", scenario=scenario)
        assert "code" in prompt.lower()
        assert "maintained" in prompt.lower()
