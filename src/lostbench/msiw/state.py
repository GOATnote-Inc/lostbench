"""EscalationState — freeze-after-lock monotonic state for MSIW."""

from dataclasses import dataclass, field


@dataclass
class EscalationState:
    """Monotonic escalation state. Once locked, all fields are frozen.

    There is no unlock, reset, or set_escalated(False) method.
    The only transition is: unlocked -> locked (via lock()).
    """

    escalated: bool = False
    escalation_reason: str | None = None
    time_to_harm: str = ""
    required_actions: list[str] = field(default_factory=list)
    resource_bundle: list[str] = field(default_factory=list)
    escalation_turn: int | None = None
    confidence: float = 0.0
    _frozen: bool = field(default=False, repr=False)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise RuntimeError(
                f"EscalationState is frozen after lock(). "
                f"Cannot set '{name}'."
            )
        object.__setattr__(self, name, value)

    def lock(
        self,
        reason: str,
        time_to_harm: str,
        actions: list[str],
        resources: list[str],
        turn: int,
        confidence: float,
    ) -> None:
        """Lock the state into escalated mode. Irreversible."""
        if self._frozen:
            return  # Already locked — idempotent
        object.__setattr__(self, "escalated", True)
        object.__setattr__(self, "escalation_reason", reason)
        object.__setattr__(self, "time_to_harm", time_to_harm)
        object.__setattr__(self, "required_actions", list(actions))
        object.__setattr__(self, "resource_bundle", list(resources))
        object.__setattr__(self, "escalation_turn", turn)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "_frozen", True)

    def snapshot(self) -> dict:
        """Return a serializable snapshot of current state."""
        return {
            "escalated": self.escalated,
            "escalation_reason": self.escalation_reason,
            "time_to_harm": self.time_to_harm,
            "required_actions": list(self.required_actions),
            "resource_bundle": list(self.resource_bundle),
            "escalation_turn": self.escalation_turn,
            "confidence": self.confidence,
        }
