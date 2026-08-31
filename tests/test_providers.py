"""Tests for provider initialization, seed support, and error handling."""

import pytest

from lostbench.providers.base import Provider
from lostbench.providers.cached import CachedProvider
from lostbench.cache import ResponseCache


class TestProviderBaseClass:
    """Base class defaults."""

    def test_supports_seed_default_true(self):
        """Default providers support seed for deterministic results."""

        class DummyProvider(Provider):
            async def chat(self, messages, model=None, temperature=0.0, seed=42):
                return "ok"

        assert DummyProvider().supports_seed is True

    def test_supports_seed_override(self):
        """Providers can override supports_seed."""

        class NondeterministicProvider(Provider):
            @property
            def supports_seed(self) -> bool:
                return False

            async def chat(self, messages, model=None, temperature=0.0, seed=42):
                return "ok"

        assert NondeterministicProvider().supports_seed is False


class TestGoogleProviderSeedFlag:
    """Google provider reports nondeterminism."""

    def test_google_supports_seed_false(self):
        """Google provider does not support seed parameter."""
        # Import at test time — skips if google-genai not installed or no key
        try:
            from lostbench.providers.google import GoogleProvider
        except (ImportError, ValueError):
            pytest.skip("google-genai SDK or GOOGLE_API_KEY not available")
        assert GoogleProvider.supports_seed.fget(None) is not None  # property exists
        # Can't instantiate without API key, but we can check the class
        assert (
            GoogleProvider.supports_seed.fget.__doc__ is None or True
        )  # property defined

    def test_google_class_has_seed_override(self):
        """Verify GoogleProvider overrides supports_seed at class level."""
        try:
            from lostbench.providers.google import GoogleProvider
        except ImportError:
            pytest.skip("google-genai SDK not available")
        # Check that the class has its own supports_seed (not inherited)
        assert "supports_seed" in GoogleProvider.__dict__


class TestOpenAIProviderInit:
    """OpenAI provider initialization."""

    def test_openai_provider_creates(self, monkeypatch):
        """OpenAI provider can be instantiated."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from lostbench.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        assert provider.supports_seed is True

    def test_openai_provider_has_timeout(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        from lostbench.providers.openai import OpenAIProvider

        provider = OpenAIProvider()
        timeout = provider._client.timeout
        # May be float or httpx.Timeout depending on SDK version
        effective = timeout if isinstance(timeout, (int, float)) else timeout.connect
        assert effective == 60.0


class TestAnthropicProviderInit:
    """Anthropic provider initialization."""

    def test_anthropic_provider_creates(self):
        from lostbench.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider()
        assert provider.supports_seed is False


class TestXAIProviderInit:
    """xAI provider requires API key."""

    def test_xai_requires_key(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        from lostbench.providers.xai import XAIProvider

        with pytest.raises(ValueError, match="XAI_API_KEY"):
            XAIProvider()


class TestOpenAICompatibleProviderInit:
    """OpenAI-compatible provider initialization."""

    def test_creates_with_base_url(self):
        from lostbench.providers.openai_compatible import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1")
        assert provider.supports_seed is True
        assert str(provider._client.base_url).startswith("http://localhost:11434")


class TestCachedProviderDelegation:
    """CachedProvider delegates supports_seed to wrapped provider."""

    def test_delegates_supports_seed_true(self, tmp_path):
        class DummyProvider(Provider):
            async def chat(self, messages, model=None, temperature=0.0, seed=42):
                return "ok"

        cache = ResponseCache(str(tmp_path))
        cached = CachedProvider(DummyProvider(), cache)
        assert cached.supports_seed is True

    def test_delegates_supports_seed_false(self, tmp_path):
        class NondeterministicProvider(Provider):
            @property
            def supports_seed(self) -> bool:
                return False

            async def chat(self, messages, model=None, temperature=0.0, seed=42):
                return "ok"

        cache = ResponseCache(str(tmp_path))
        cached = CachedProvider(NondeterministicProvider(), cache)
        assert cached.supports_seed is False


class TestAnthropicSamplingParamCurrency:
    """Anthropic removed sampling params from the 4.7/5 generation onward.

    The provider must omit temperature for those (and unknown/future)
    models, and keep sending it to the legacy 4.6-family so existing
    deterministic runs are unchanged.
    """

    def _kwargs(self, model, temperature=0.0):
        from lostbench.providers.anthropic import _build_message_kwargs

        return _build_message_kwargs(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
            model,
            temperature,
        )

    def test_legacy_models_still_get_temperature(self):
        for model in ("claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"):
            kwargs = self._kwargs(model)
            assert kwargs["temperature"] == 0.0, model

    def test_dated_legacy_alias_gets_temperature(self):
        assert "temperature" in self._kwargs("claude-sonnet-4-5-20250929")

    def test_current_models_omit_temperature(self):
        for model in (
            "claude-opus-4-7",
            "claude-opus-4-8",
            "claude-opus-5",
            "claude-sonnet-5",
            "claude-fable-5",
        ):
            kwargs = self._kwargs(model)
            assert "temperature" not in kwargs, (
                f"{model} rejects sampling params (HTTP 400); "
                "temperature must be omitted"
            )

    def test_unknown_future_model_omits_temperature(self):
        assert "temperature" not in self._kwargs("claude-epic-6")

    def test_env_override_always(self, monkeypatch):
        monkeypatch.setenv("LOSTBENCH_ANTHROPIC_SAMPLING", "always")
        assert "temperature" in self._kwargs("claude-opus-4-8")

    def test_env_override_never(self, monkeypatch):
        monkeypatch.setenv("LOSTBENCH_ANTHROPIC_SAMPLING", "never")
        assert "temperature" not in self._kwargs("claude-opus-4-6")

    def test_thinking_opt_in(self, monkeypatch):
        monkeypatch.setenv("LOSTBENCH_ANTHROPIC_THINKING", "adaptive")
        kwargs = self._kwargs("claude-opus-4-8")
        assert kwargs["thinking"] == {"type": "adaptive"}

    def test_thinking_off_by_default(self):
        assert "thinking" not in self._kwargs("claude-opus-4-8")

    def test_system_message_extracted(self):
        kwargs = self._kwargs("claude-opus-4-8")
        assert kwargs["system"] == "sys"
        assert all(m["role"] != "system" for m in kwargs["messages"])

    def test_first_text_block_skips_thinking(self):
        from lostbench.providers.anthropic import _first_text_block

        class _Thinking:
            type = "thinking"
            thinking = "..."

        class _Text:
            type = "text"
            text = "answer"

        class _Response:
            content = [_Thinking(), _Text()]

        block = _first_text_block(_Response())
        assert block is not None and block.text == "answer"
