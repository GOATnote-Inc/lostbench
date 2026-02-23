"""CEIS evaluation configuration — YAML schema and loader.

Provides a structured configuration for running CEIS evaluations.
A CEISConfig loads from a YAML file and produces a RunConfig for the
existing LostBench runner infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from lostbench.config import RunConfig


@dataclass(frozen=True)
class CEISConfig:
    """Complete configuration for a CEIS evaluation run."""

    # Target model
    model: str
    provider: str
    system_prompt_path: str | None = None

    # Determinism (locked defaults per spec)
    temperature: float = 0.0
    seed: int = 42
    max_tokens: int = 4096

    # Corpus
    corpus: str = "emergency"
    n_trials: int = 3
    conditions: list[str] | None = None

    # Mitigation (optional)
    wrapper_enabled: bool = False
    wrapper_preamble: bool = True
    inject_preamble: bool = False

    # Judge
    judge_model: str | None = None

    # RAG (optional)
    rag_corpus_path: str | None = None

    # Prior version for regression detection (optional)
    prior_results_path: str | None = None
    prior_model_id: str | None = None

    # Output
    output_dir: str = "."
    output_formats: list[str] = field(default_factory=lambda: ["json"])

    def validate(self) -> list[str]:
        """Validate configuration, returning a list of error messages."""
        errors: list[str] = []

        if not self.model:
            errors.append("model is required")
        if not self.provider:
            errors.append("provider is required")
        if self.provider not in (
            "openai",
            "anthropic",
            "xai",
            "google",
            "openai-compatible",
        ):
            errors.append(
                f"provider must be one of openai/anthropic/xai/google/openai-compatible, got '{self.provider}'"
            )
        if self.temperature != 0.0:
            errors.append(
                f"CEIS requires temperature=0.0 for determinism, got {self.temperature}"
            )
        if self.n_trials < 1:
            errors.append(f"n_trials must be >= 1, got {self.n_trials}")
        if self.corpus not in ("emergency", "crisis-resource", "defer", "adversarial"):
            errors.append(
                f"corpus must be emergency/crisis-resource/defer, got '{self.corpus}'"
            )
        if self.system_prompt_path and not Path(self.system_prompt_path).exists():
            errors.append(
                f"system_prompt_path does not exist: {self.system_prompt_path}"
            )
        if self.prior_results_path and not Path(self.prior_results_path).exists():
            errors.append(
                f"prior_results_path does not exist: {self.prior_results_path}"
            )
        if self.rag_corpus_path and not Path(self.rag_corpus_path).exists():
            errors.append(f"rag_corpus_path does not exist: {self.rag_corpus_path}")
        if self.inject_preamble and self.wrapper_enabled:
            errors.append("inject_preamble and wrapper_enabled are mutually exclusive")

        valid_formats = {"json", "text", "markdown"}
        for fmt in self.output_formats:
            if fmt not in valid_formats:
                errors.append(
                    f"output_format '{fmt}' not supported (use json/text/markdown)"
                )

        return errors

    def to_run_config(self) -> RunConfig:
        """Convert to a RunConfig for the existing LostBench runner."""
        return RunConfig(
            model=self.model,
            provider=self.provider,
            corpus=self.corpus,
            trials=self.n_trials,
            system_prompt_path=self.system_prompt_path,
            judge_model=self.judge_model,
            conditions=self.conditions,
            pattern_only=False,
            temperature=self.temperature,
            seed=self.seed,
            output_dir=self.output_dir,
            wrapper_enabled=self.wrapper_enabled,
            wrapper_preamble=self.wrapper_preamble,
            inject_preamble=self.inject_preamble,
            rag_corpus_path=self.rag_corpus_path,
        )


def load_ceis_config(path: str | Path) -> CEISConfig:
    """Load a CEIS configuration from a YAML file.

    Example YAML:

        model: gpt-5.2
        provider: openai
        corpus: emergency
        n_trials: 3
        output_dir: ./ceis-output
        output_formats: [json, text]

        # Optional: prior version for regression detection
        prior_results_path: ./prior-results.json
        prior_model_id: gpt-5.1
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CEIS config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"CEIS config must be a YAML mapping, got {type(raw).__name__}"
        )

    # Extract fields with defaults
    conditions = raw.get("conditions")
    if isinstance(conditions, str):
        conditions = [c.strip() for c in conditions.split(",")]

    output_formats = raw.get("output_formats", ["json"])
    if isinstance(output_formats, str):
        output_formats = [output_formats]

    return CEISConfig(
        model=raw.get("model", ""),
        provider=raw.get("provider", ""),
        system_prompt_path=raw.get("system_prompt_path"),
        temperature=float(raw.get("temperature", 0.0)),
        seed=int(raw.get("seed", 42)),
        max_tokens=int(raw.get("max_tokens", 4096)),
        corpus=raw.get("corpus", "emergency"),
        n_trials=int(raw.get("n_trials", 3)),
        conditions=conditions,
        wrapper_enabled=bool(raw.get("wrapper_enabled", False)),
        wrapper_preamble=bool(raw.get("wrapper_preamble", True)),
        inject_preamble=bool(raw.get("inject_preamble", False)),
        judge_model=raw.get("judge_model"),
        rag_corpus_path=raw.get("rag_corpus_path"),
        prior_results_path=raw.get("prior_results_path"),
        prior_model_id=raw.get("prior_model_id"),
        output_dir=raw.get("output_dir", "."),
        output_formats=output_formats,
    )
