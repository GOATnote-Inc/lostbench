"""Base provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatResponse:
    """Rich response from a provider, preserving API metadata for provenance."""

    text: str
    model_version: str = ""
    request_id: str = ""
    usage: dict = field(default_factory=dict)
    raw_body: str = ""


class Provider(ABC):
    """Abstract base class for model providers."""

    @property
    def supports_seed(self) -> bool:
        """Whether this provider supports deterministic seeding.

        Providers that return False will have their results flagged as
        nondeterministic in the run manifest.
        """
        return True

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> str:
        """Send messages and return assistant response text."""
        ...

    async def chat_rich(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
        seed: int = 42,
    ) -> ChatResponse:
        """Send messages and return rich response with API metadata.

        Default implementation wraps chat(). Providers override to capture
        request_id, model_version, usage, and raw response body.
        """
        text = await self.chat(messages, model, temperature, seed)
        return ChatResponse(text=text, model_version=model or "")
