"""Provider adapters for LostBench."""

from lostbench.providers.base import Provider
from lostbench.providers.openai import OpenAIProvider
from lostbench.providers.anthropic import AnthropicProvider
from lostbench.providers.xai import XAIProvider


PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "xai": XAIProvider,
}


def get_provider(name: str) -> Provider:
    cls = PROVIDER_MAP.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}. Available: {list(PROVIDER_MAP.keys())}")
    return cls()
