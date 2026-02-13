"""Configuration for LostBench."""

from dataclasses import dataclass
from pathlib import Path
import hashlib


PACKAGE_ROOT = Path(__file__).parent.parent.parent
PROMPTS_DIR = PACKAGE_ROOT / "prompts"
SCENARIOS_DIR = PACKAGE_ROOT / "scenarios"

DEFAULT_JUDGE_MODEL = "claude-opus-4-6-20250918"
DEFAULT_JUDGE_FALLBACK = "gpt-5.2"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 42
DEFAULT_TRIALS = 3


@dataclass
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

    @property
    def system_prompt(self) -> str:
        if self.system_prompt_path:
            return Path(self.system_prompt_path).read_text().strip()
        return (PROMPTS_DIR / "default.txt").read_text().strip()

    @property
    def system_prompt_hash(self) -> str:
        return hashlib.sha256(self.system_prompt.encode()).hexdigest()

    @property
    def resolved_judge_model(self) -> str:
        if self.judge_model:
            return self.judge_model
        if self.model == DEFAULT_JUDGE_MODEL:
            return DEFAULT_JUDGE_FALLBACK
        return DEFAULT_JUDGE_MODEL

    @property
    def judge_override(self) -> bool:
        return self.judge_model is None and self.model == DEFAULT_JUDGE_MODEL

    @property
    def judge_fallback_reason(self) -> str | None:
        if self.judge_override:
            return "self-judge conflict"
        return None

    @property
    def mode(self) -> str:
        return "pattern-only" if self.pattern_only else "benchmark"

    def validate(self) -> None:
        if self.judge_model and self.judge_model == self.model:
            raise SystemExit("Judge model must differ from tested model.")
