"""Audit event dataclass for MSIW wrapper."""

from dataclasses import dataclass, field


@dataclass
class AuditEvent:
    """Record of wrapper enforcement activity for a single turn."""

    turn_index: int
    escalated: bool
    state_changed: bool
    trigger_patterns: list[str] = field(default_factory=list)
    tier0_violations: list[str] = field(default_factory=list)
    tier1_scores: dict[str, float] = field(default_factory=dict)
    all_violations: list[str] = field(default_factory=list)
    replaced: bool = False
    template_id: str | None = None
    template_hash: str | None = None
