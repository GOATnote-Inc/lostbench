"""Google Gemini provider adapter."""

import os
import sys

from google import genai
from google.genai import types

from lostbench.providers.base import Provider
from lostbench.retry import retry_with_backoff


class GoogleProvider(Provider):
    """Google Gemini provider using the google-genai SDK."""

    @property
    def supports_seed(self) -> bool:
        return False

    def __init__(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY environment variable is required for Google provider"
            )
        self._client = genai.Client(api_key=api_key)

    async def chat(self, messages: list[dict], model: str | None = None,
                   temperature: float = 0.0, seed: int = 42) -> str:
        system_instruction = None
        contents = []

        for m in messages:
            if m["role"] == "system":
                if system_instruction is not None:
                    raise ValueError(
                        "Google provider expects at most one system message"
                    )
                system_instruction = m["content"]
            elif m["role"] == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=m["content"])],
                ))
            elif m["role"] == "assistant":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=m["content"])],
                ))

        config = types.GenerateContentConfig(
            temperature=temperature,
            httpOptions=types.HttpOptions(timeout=60_000),
        )
        if system_instruction:
            config.system_instruction = system_instruction

        # Seed not supported in google-genai SDK — log once
        if seed != 42:
            print(
                f"  [google] seed={seed} requested but google-genai SDK does not "
                f"support seed parameter; result may not be deterministic",
                file=sys.stderr,
            )

        async def _call():
            return await self._client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

        response = await retry_with_backoff(_call)

        if not response.text:
            raise ValueError(f"Empty response from Google API (model={model})")
        return response.text
