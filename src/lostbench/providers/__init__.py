"""Provider adapters for LostBench."""

from lostbench.providers.base import ChatResponse as ChatResponse, Provider
from lostbench.providers.openai import OpenAIProvider
from lostbench.providers.anthropic import AnthropicProvider
from lostbench.providers.xai import XAIProvider
from lostbench.providers.google import GoogleProvider
from lostbench.providers.openai_compatible import OpenAICompatibleProvider


PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "xai": XAIProvider,
    "google": GoogleProvider,
    "openai-compatible": OpenAICompatibleProvider,
}


def get_provider(name: str, **kwargs) -> Provider:
    cls = PROVIDER_MAP.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown provider: {name}. Available: {list(PROVIDER_MAP.keys())}"
        )
    if kwargs:
        return cls(**kwargs)
    return cls()
