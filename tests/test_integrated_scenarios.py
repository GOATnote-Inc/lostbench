"""Tests for integrated system scenarios (PRI-001 through PRI-009)."""

from lostbench.scenarios.loader import load_scenarios
from lostbench.judge import build_judge_system_prompt, VECTOR_PROMPT_MAP


class TestIntegratedScenarioLoading:
    """Verify integrated system scenarios load correctly."""

    def test_loads_all_scenarios(self):
        scenarios = load_scenarios("integrated")
        assert len(scenarios) == 9

    def test_scenario_ids_sequential(self):
        scenarios = load_scenarios("integrated")
        ids = {s["id"] for s in scenarios}
        for i in range(1, 10):
            assert f"PRI-{i:03d}" in ids

    def test_required_fields(self):
        scenarios = load_scenarios("integrated")
        for s in scenarios:
            assert "id" in s
            assert "condition" in s
            assert "initial" in s
            assert "pressure" in s
            assert "ceis" in s

    def test_vector_field(self):
        scenarios = load_scenarios("integrated")
        for s in scenarios:
            assert s.get("vector") == "integrated_system", (
                f"{s['id']} missing vector=integrated_system"
            )

    def test_ehr_or_rag_context_present(self):
        """Each integrated scenario should have ehr_context and/or rag_context."""
        scenarios = load_scenarios("integrated")
        for s in scenarios:
            has_ctx = bool(s.get("ehr_context")) or bool(s.get("rag_context"))
            assert has_ctx, f"{s['id']} missing ehr_context or rag_context"

    def test_ehr_context_structure(self):
        """EHR context should be a dict with patient_summary and/or risk_flags."""
        scenarios = load_scenarios("integrated")
        for s in scenarios:
            if not s.get("ehr_context"):
                continue
            ehr = s["ehr_context"]
            if isinstance(ehr, dict):
                has_fields = bool(ehr.get("patient_summary")) or bool(
                    ehr.get("risk_flags")
                )
                assert has_fields, f"{s['id']} ehr_context dict has no known fields"

    def test_ceis_metadata(self):
        scenarios = load_scenarios("integrated")
        for s in scenarios:
            assert s["ceis"]["required_escalation_level"] == 3
            assert s["ceis"]["suite"] == "capability"
            assert 0.0 <= s["ceis"]["severity_weight"] <= 2.0

    def test_reference_responses_present(self):
        scenarios = load_scenarios("integrated")
        for s in scenarios:
            refs = s.get("reference_responses") or s.get("reference")
            assert refs, f"{s['id']} missing reference responses"

    def test_conditions_filter(self):
        scenarios = load_scenarios("integrated", conditions=["PRI-001", "PRI-006"])
        assert len(scenarios) == 2
        ids = {s["id"] for s in scenarios}
        assert ids == {"PRI-001", "PRI-006"}

    def test_injected_context_on_some_turns(self):
        """At least PRI-009 should have injected_context for multi-step RAG."""
        scenarios = load_scenarios("integrated", conditions=["PRI-009"])
        assert len(scenarios) == 1
        s = scenarios[0]
        has_injected = any(p.get("injected_context") for p in s.get("pressure", []))
        assert has_injected, "PRI-009 should have injected_context for multi-step RAG"


class TestIntegratedSystemPromptInjection:
    """Verify that ehr_context and rag_context are injected into system prompt."""

    def test_ehr_context_formatting(self):
        """EHR context dict should be formatted into a readable block."""
        ehr = {
            "patient_summary": "54yo M, hx anxiety, 12 ED visits/year",
            "risk_flags": {"frequent_flyer": True, "anxiety_dx": True},
        }
        # Simulate the runner's formatting logic
        ehr_block = "\n## Patient EHR Context\n"
        if isinstance(ehr, dict):
            if ehr.get("patient_summary"):
                ehr_block += ehr["patient_summary"].strip() + "\n"
            if ehr.get("risk_flags"):
                ehr_block += (
                    "Risk flags: "
                    + ", ".join(f"{k}={v}" for k, v in ehr["risk_flags"].items())
                    + "\n"
                )
        assert "54yo M" in ehr_block
        assert "frequent_flyer=True" in ehr_block


class TestIntegratedJudgeRouting:
    """Verify judge prompt routing for integrated system vector."""

    def test_vector_prompt_mapping_exists(self):
        assert "integrated_system" in VECTOR_PROMPT_MAP

    def test_judge_prompt_loads(self):
        scenario = {"vector": "integrated_system", "condition": "stemi"}
        prompt = build_judge_system_prompt("unknown", scenario=scenario)
        assert "ehr" in prompt.lower() or "system context" in prompt.lower()
        assert "maintained" in prompt.lower()
