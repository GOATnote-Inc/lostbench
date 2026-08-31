"""Monotonic Safety Invariant Wrapper (MSIW) — runtime enforcement layer.

Research instrument only: MSIW exists to measure the effect of runtime
mitigation inside the LostBench evaluation harness. It is NOT a deployable
clinical safety layer, is not a medical device, and must not be used to
mediate real patient conversations.
"""

from lostbench.msiw.wrapper import MonotonicSafetyWrapper, WrapperResult
from lostbench.msiw.state import EscalationState
from lostbench.msiw.audit import AuditEvent

__all__ = [
    "MonotonicSafetyWrapper",
    "WrapperResult",
    "EscalationState",
    "AuditEvent",
]
