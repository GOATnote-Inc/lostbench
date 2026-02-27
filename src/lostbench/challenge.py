"""Challenge — Atomic single-scenario engagement.

Runs one model against one scenario for k trials, producing a transcript JSON.
No grading — just raw conversation capture. The atomic unit of the campaign engine.

Usage:
    from lostbench.challenge import run_challenge
    result = await run_challenge(scenario, provider, model, n_trials=5)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from lostbench.providers.base import Provider

logger = logging.getLogger(__name__)


@dataclass
class ChallengeTranscript:
    """Raw transcript from a single trial of a single scenario."""

    trial: int
    messages: list[dict]
    responses: list[str]


@dataclass
class ChallengeResult:
    """Result of running a challenge: one model, one scenario, k trials."""

    scenario_id: str
    condition: str
    model: str
    n_trials: int
    temperature: float
    seed: int
    timestamp: str
    transcripts: list[ChallengeTranscript] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "condition": self.condition,
            "model": self.model,
            "n_trials": self.n_trials,
            "temperature": self.temperature,
            "seed": self.seed,
            "timestamp": self.timestamp,
            "transcripts": [asdict(t) for t in self.transcripts],
            "metadata": self.metadata,
        }

    def save(self, output_dir: str | Path) -> Path:
        """Write challenge result to JSON file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize model name for filename
        model_safe = self.model.replace("/", "-").replace(" ", "_")
        path = output_dir / f"challenge_{self.scenario_id}_{model_safe}.json"
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Challenge saved: %s", path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "ChallengeResult":
        """Load a challenge result from JSON."""
        with open(path) as f:
            data = json.load(f)
        transcripts = [ChallengeTranscript(**t) for t in data.pop("transcripts", [])]
        return cls(**data, transcripts=transcripts)


def _build_conversation(scenario: dict, system_prompt: str | None = None) -> list[dict]:
    """Build the initial message list from a scenario.

    Returns list of (role, content) messages representing the
    conversation setup before the first model response.
    """
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": scenario["initial"]})
    return messages


async def _run_single_trial(
    scenario: dict,
    provider: Provider,
    model: str,
    trial_idx: int,
    temperature: float = 0.0,
    seed: int = 42,
    system_prompt: str | None = None,
) -> ChallengeTranscript:
    """Run one trial: initial + pressure turns, capturing all responses."""
    messages = _build_conversation(scenario, system_prompt)
    responses: list[str] = []

    # Initial response
    response = await provider.chat(
        messages, model=model, temperature=temperature, seed=seed
    )
    responses.append(response)
    messages.append({"role": "assistant", "content": response})

    # Pressure turns
    pressure_turns = scenario.get("pressure", [])
    for pressure in pressure_turns:
        content = pressure.get("content", "")
        if not content:
            continue
        messages.append({"role": "user", "content": content})
        response = await provider.chat(
            messages, model=model, temperature=temperature, seed=seed
        )
        responses.append(response)
        messages.append({"role": "assistant", "content": response})

    return ChallengeTranscript(
        trial=trial_idx,
        messages=messages,
        responses=responses,
    )


async def run_challenge(
    scenario: dict,
    provider: Provider,
    model: str,
    n_trials: int = 5,
    temperature: float = 0.0,
    seed: int = 42,
    system_prompt: str | None = None,
) -> ChallengeResult:
    """Run a challenge: one model, one scenario, k trials.

    Args:
        scenario: Scenario dict (must have 'id', 'condition', 'initial', 'pressure').
        provider: Model provider for API calls.
        model: Model identifier string.
        n_trials: Number of independent trials.
        temperature: Sampling temperature (0.0 for determinism).
        seed: Random seed for reproducibility.
        system_prompt: Optional system prompt override.

    Returns:
        ChallengeResult with raw transcripts (no grading).
    """
    sid = scenario["id"]
    condition = scenario.get("condition", "unknown")
    logger.info("Challenge %s (%s) x %d trials", sid, condition, n_trials)

    transcripts: list[ChallengeTranscript] = []
    for trial_idx in range(n_trials):
        transcript = await _run_single_trial(
            scenario=scenario,
            provider=provider,
            model=model,
            trial_idx=trial_idx,
            temperature=temperature,
            seed=seed,
            system_prompt=system_prompt,
        )
        transcripts.append(transcript)
        logger.debug(
            "  Trial %d/%d: %d responses captured",
            trial_idx + 1,
            n_trials,
            len(transcript.responses),
        )

    return ChallengeResult(
        scenario_id=sid,
        condition=condition,
        model=model,
        n_trials=n_trials,
        temperature=temperature,
        seed=seed,
        timestamp=datetime.now(timezone.utc).isoformat(),
        transcripts=transcripts,
        metadata={
            "pressure_count": len(scenario.get("pressure", [])),
            "corpus": scenario.get("corpus", ""),
        },
    )
