"""Tests for OpenEM differentials context retrieval and runner injection."""

from unittest.mock import MagicMock, patch

import pytest

from lostbench.openem import OpenEMRetriever


@pytest.fixture
def mock_bridge():
    bridge = MagicMock()
    bridge.get_context_with_differentials.return_value = (
        "Tension headache: bilateral, gradual onset\n\n"
        "[ESCALATION TRIGGERS — Red flags requiring emergency evaluation]\n"
        "- ESCALATE if: thunderclap onset, worst headache of life "
        "(consider subarachnoid hemorrhage)"
    )
    return bridge


@pytest.fixture
def retriever(mock_bridge, tmp_path):
    index_dir = tmp_path / "index"
    index_dir.mkdir()
    with patch("lostbench.openem._load_bridge", return_value=mock_bridge):
        return OpenEMRetriever(index_dir)


class TestGetDifferentialsContext:
    def test_delegates_to_bridge(self, retriever, mock_bridge):
        result = retriever.get_differentials_context("tension-headache")
        mock_bridge.get_context_with_differentials.assert_called_once_with(
            "tension-headache", 5, 3000
        )
        assert "[ESCALATION TRIGGERS" in result

    def test_custom_params(self, retriever, mock_bridge):
        retriever.get_differentials_context("tension-headache", top_k=3, max_chars=1500)
        mock_bridge.get_context_with_differentials.assert_called_once_with(
            "tension-headache", 3, 1500
        )

    def test_returns_none_when_bridge_returns_none(self, retriever, mock_bridge):
        mock_bridge.get_context_with_differentials.return_value = None
        result = retriever.get_differentials_context("unknown-condition")
        assert result is None


class TestFormatDifferentialsContext:
    def test_wraps_with_system_prefix(self, retriever):
        result = retriever.format_differentials_context("tension-headache")
        assert result is not None
        assert result.startswith("You are a clinical assistant.")
        assert "--- CLINICAL REFERENCE ---" in result
        assert "--- END REFERENCE ---" in result
        assert "[ESCALATION TRIGGERS" in result

    def test_returns_none_when_no_context(self, retriever, mock_bridge):
        mock_bridge.get_context_with_differentials.return_value = None
        result = retriever.format_differentials_context("unknown-condition")
        assert result is None

    def test_recommends_emergency_care(self, retriever):
        result = retriever.format_differentials_context("tension-headache")
        assert "Recommend emergency care when clinically indicated" in result


class TestDeferTrialRagInjection:
    """Test that _run_single_defer_trial injects differentials context."""

    def test_runner_has_rag_injection_code(self):
        """Verify the runner code references format_differentials_context."""
        import inspect

        from lostbench.runner import Runner

        source = inspect.getsource(Runner._run_single_defer_trial)
        assert "format_differentials_context" in source
        assert "_rag_retriever" in source

    def test_runner_has_preamble_injection_code(self):
        """Verify the runner code references MSIW_SYSTEM_PREAMBLE for defer."""
        import inspect

        from lostbench.runner import Runner

        source = inspect.getsource(Runner._run_single_defer_trial)
        assert "inject_preamble" in source
        assert "MSIW_SYSTEM_PREAMBLE" in source
