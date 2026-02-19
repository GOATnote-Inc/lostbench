"""Configuration for LostBench."""

from dataclasses import dataclass
from pathlib import Path
import hashlib


_PACKAGE_DIR = Path(__file__).parent
PROMPTS_DIR = _PACKAGE_DIR / "prompts"
SCENARIOS_DIR = _PACKAGE_DIR / "scenarios"

DEFAULT_JUDGE_MODEL = "claude-opus-4-6"
DEFAULT_JUDGE_FALLBACK = "gpt-5.2"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 42
DEFAULT_TRIALS = 3

# Cross-vendor judge selection (from ScribeGoat2 bloom_grader.py)
VENDOR_PATTERNS: dict[str, str] = {
    "claude": "anthropic",
    "gpt": "openai",
    "o1": "openai",
    "o4": "openai",
    "gemini": "google",
    "grok": "xai",
}

# NOTE: Cross-vendor judging has not been calibrated for inter-judge agreement.
# GPT-5.2 judges Opus; Opus judges GPT/Sonnet. This asymmetry means scores
# are not directly comparable across models without calibration data.
# See PHASE3_FINDINGS.md section on judge selection for details.
CROSS_VENDOR_JUDGE_MAP: dict[str, str] = {
    "anthropic": "gpt-5.2",
    "openai": "claude-opus-4-6",
    "xai": "claude-opus-4-6",
    "google": "claude-opus-4-6",
}


def _detect_vendor(model_id: str) -> str | None:
    """Detect vendor from model ID string."""
    model_lower = model_id.lower()
    for pattern, vendor in VENDOR_PATTERNS.items():
        if pattern in model_lower:
            return vendor
    return None


@dataclass(frozen=True)
class RunConfig:
    model: str
    provider: str
    corpus: str = "emergency"
    trials: int = DEFAULT_TRIALS
    system_prompt_path: str | None = None
    judge_model: str | None = None
    conditions: list[str] | None = None
    pattern_only: bool = False
    temperature: float = DEFAULT_TEMPERATURE
    seed: int = DEFAULT_SEED
    output_dir: str = "."
    wrapper_enabled: bool = False
    wrapper_preamble: bool = True
    inject_preamble: bool = False
    rag_corpus_path: str | None = None

    @property
    def system_prompt(self) -> str:
        if self.system_prompt_path:
            return Path(self.system_prompt_path).read_text().strip()
        return (PROMPTS_DIR / "default.txt").read_text().strip()

    @property
    def system_prompt_hash(self) -> str:
        return hashlib.sha256(self.system_prompt.encode()).hexdigest()

    @staticmethod
    def _is_same_model_family(model_a: str, model_b: str) -> bool:
        """Check if two model IDs refer to the same model (one may be a dated alias)."""
        return model_a == model_b or model_a.startswith(model_b) or model_b.startswith(model_a)

    @property
    def resolved_judge_model(self) -> str:
        if self.judge_model:
            return self.judge_model
        # Use vendor detection for cross-vendor judge selection
        model_vendor = _detect_vendor(self.model)
        if model_vendor and model_vendor in CROSS_VENDOR_JUDGE_MAP:
            return CROSS_VENDOR_JUDGE_MAP[model_vendor]
        # Fallback: prefix-matching for unknown vendors
        if self._is_same_model_family(self.model, DEFAULT_JUDGE_MODEL):
            return DEFAULT_JUDGE_FALLBACK
        return DEFAULT_JUDGE_MODEL

    @property
    def judge_override(self) -> bool:
        if self.judge_model is not None:
            return False
        model_vendor = _detect_vendor(self.model)
        judge_vendor = _detect_vendor(self.resolved_judge_model)
        if model_vendor and judge_vendor:
            return model_vendor == judge_vendor
        return self._is_same_model_family(self.model, DEFAULT_JUDGE_MODEL)

    @property
    def judge_fallback_reason(self) -> str | None:
        if self.judge_override:
            return "self-judge conflict"
        return None

    @property
    def mode(self) -> str:
        base = ""
        if self.inject_preamble:
            base = "preamble-only"
        elif self.wrapper_enabled:
            if not self.wrapper_preamble:
                base = "enforce-only"
            else:
                base = "wrapper"
        else:
            base = "pattern-only" if self.pattern_only else "benchmark"
        if self.rag_corpus_path:
            return f"{base}+rag"
        return base

    def validate(self) -> None:
        if self.judge_model and self.judge_model == self.model:
            raise SystemExit("Judge model must differ from tested model.")
