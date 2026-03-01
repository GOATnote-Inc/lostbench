"""Simplified evaluation entry point — wraps CEIS pipeline with preset modes.

Three modes with increasing coverage and cost:
  quick    - 8 CI scenarios, 1 trial, pattern-only (~30s, ~$0.10)
  standard - 28 new-cohort scenarios, 3 trials, full CEIS (~5 min, ~$5)
  full     - 78 emergency scenarios, 3 trials, full CEIS (~20 min, ~$15)

Usage:
    from lostbench.evaluate import run_evaluation, EvaluationConfig, EvaluationMode

    config = EvaluationConfig(
        model="gpt-5.2",
        provider="openai",
        mode=EvaluationMode.STANDARD,
    )
    result = run_evaluation(config)
    print(format_report(result))
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lostbench.ceis_config import CEISConfig
from lostbench.config import CROSS_VENDOR_JUDGE_MAP, _detect_vendor

logger = logging.getLogger(__name__)


class EvaluationMode(Enum):
    """Preset evaluation modes with increasing coverage."""

    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"


# CI subset: diverse published scenarios for smoke testing
_QUICK_CONDITIONS = [
    "MTR-001",
    "MTR-004",
    "MTR-006",
    "MTR-009",
    "MTR-012",
    "MTR-015",
    "MTR-018",
    "MTR-022",
]

# New cohort: expanded corpus scenarios
_STANDARD_CONDITIONS = [
    "MTR-001",
    "MTR-004",
    "MTR-006",
    "MTR-009",
    "MTR-012",
    "MTR-015",
    "MTR-018",
    "MTR-022",
    "MTR-024",
    "MTR-027",
    "MTR-030",
    "MTR-033",
    "MTR-036",
    "MTR-039",
    "MTR-042",
    "MTR-045",
    "MTR-048",
    "MTR-051",
    "MTR-054",
    "MTR-057",
    "MTR-060",
    "MTR-063",
    "MTR-066",
    "MTR-069",
    "MTR-072",
    "MTR-075",
    "MTR-078",
    "MTR-003",
]

# Mode presets: (conditions, n_trials, pattern_only)
_MODE_PRESETS: dict[EvaluationMode, dict[str, Any]] = {
    EvaluationMode.QUICK: {
        "conditions": _QUICK_CONDITIONS,
        "n_trials": 1,
        "pattern_only": True,
    },
    EvaluationMode.STANDARD: {
        "conditions": _STANDARD_CONDITIONS,
        "n_trials": 3,
        "pattern_only": False,
    },
    EvaluationMode.FULL: {
        "conditions": None,  # All emergency scenarios
        "n_trials": 3,
        "pattern_only": False,
    },
}


@dataclass
class EvaluationConfig:
    """Configuration for a simplified evaluation run."""

    model: str
    provider: str
    mode: EvaluationMode = EvaluationMode.STANDARD

    # Optional overrides
    base_url: str | None = None
    api_key: str | None = None
    judge_model: str | None = None
    output_dir: str = "."
    system_prompt_path: str | None = None

    def to_ceis_config(self) -> CEISConfig:
        """Convert to a full CEISConfig using mode presets."""
        preset = _MODE_PRESETS[self.mode]

        # Auto-select cross-vendor judge
        judge = self.judge_model
        if judge is None and not preset["pattern_only"]:
            vendor = _detect_vendor(self.model)
            if vendor and vendor in CROSS_VENDOR_JUDGE_MAP:
                judge = CROSS_VENDOR_JUDGE_MAP[vendor]

        return CEISConfig(
            model=self.model,
            provider=self.provider,
            system_prompt_path=self.system_prompt_path,
            corpus="emergency",
            n_trials=preset["n_trials"],
            conditions=preset["conditions"],
            judge_model=judge,
            output_dir=self.output_dir,
        )

    def validate(self) -> list[str]:
        """Validate configuration."""
        errors: list[str] = []
        if not self.model:
            errors.append("model is required")
        if not self.provider:
            errors.append("provider is required")
        valid_providers = {"openai", "anthropic", "xai", "google", "openai-compatible"}
        if self.provider not in valid_providers:
            errors.append(
                f"provider must be one of {'/'.join(sorted(valid_providers))}"
            )
        return errors


def run_evaluation(config: EvaluationConfig) -> dict:
    """Run a simplified evaluation and return results.

    Wraps the existing CEIS pipeline — no duplicated logic.

    Args:
        config: Evaluation configuration with model, provider, and mode.

    Returns:
        Dict with evaluation results (same structure as CEIS results).
    """
    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid config: {'; '.join(errors)}")

    ceis_config = config.to_ceis_config()
    ceis_errors = ceis_config.validate()
    if ceis_errors:
        raise ValueError(f"Invalid CEIS config: {'; '.join(ceis_errors)}")

    run_config = ceis_config.to_run_config()
    run_config.validate()

    # Import runner and execute
    from lostbench.runner import Runner

    runner = Runner(run_config)
    result = asyncio.run(runner.run())
    return result


def format_report(result: dict, mode: EvaluationMode | None = None) -> str:
    """Format evaluation results as a human-readable summary.

    Args:
        result: Raw result dict from run_evaluation().
        mode: Optional mode for context in the header.

    Returns:
        Formatted report string.
    """
    lines = []

    mode_label = mode.value if mode else "evaluation"
    lines.append(f"=== LostBench {mode_label} Results ===\n")

    # Extract key metrics
    model = result.get("model", "unknown")
    provider = result.get("provider", "unknown")
    lines.append(f"Model: {model} ({provider})")

    # Pass^k
    pass_k = result.get("pass_k")
    if pass_k is not None:
        lines.append(f"Pass^k: {pass_k:.3f}")

    # ERS
    ers = result.get("ers")
    if ers is not None:
        ers_ci = result.get("ers_bootstrap_ci", [])
        if ers_ci and len(ers_ci) == 2:
            lines.append(f"ERS: {ers} [{ers_ci[0]}, {ers_ci[1]}]")
        else:
            lines.append(f"ERS: {ers}")

    # Failure classes
    class_a = result.get("total_classA", 0)
    class_b = result.get("total_classB", 0)
    class_c = result.get("total_classC", 0)
    class_d = result.get("total_classD", 0)
    if any([class_a, class_b, class_c, class_d]):
        lines.append(f"Failures: A={class_a} B={class_b} C={class_c} D={class_d}")

    # Threshold
    meets = result.get("meets_threshold")
    if meets is not None:
        lines.append(f"Threshold: {'PASS' if meets else 'FAIL'}")

    # Scenarios
    conditions = result.get("conditions", {})
    if conditions:
        total = len(conditions)
        passed = sum(
            1 for c in conditions.values() if isinstance(c, dict) and c.get("passed")
        )
        lines.append(f"Scenarios: {passed}/{total} passed")

    # Judge info
    judge = result.get("grading_metadata", {}).get("judge_model", "")
    if judge:
        lines.append(f"Judge: {judge}")

    return "\n".join(lines)
