"""Base provider interface."""

from abc import ABC, abstractmethod


class Provider(ABC):
    """Abstract base class for model providers."""

    @abstractmethod
    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.0, seed: int = 42) -> str:
        """Send messages and return assistant response text."""
        ...
