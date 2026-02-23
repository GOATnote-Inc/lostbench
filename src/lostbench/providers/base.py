"""Base provider interface."""

from abc import ABC, abstractmethod


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
