"""Barrier-aware safe response templates for MSIW.

Templates are Python constants hashed at module load time.
No YAML dependency.
"""

import hashlib

TEMPLATE_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Static fallback — hardcoded, cannot fail
# ---------------------------------------------------------------------------

STATIC_FALLBACK = (
    "This situation requires immediate emergency medical evaluation. "
    "Please call 911 or go to the nearest emergency department now. "
    "If you are in crisis, call 988 (Suicide and Crisis Lifeline) "
    "or text HOME to 741741 (Crisis Text Line)."
)


# ---------------------------------------------------------------------------
# Barrier-specific templates
# ---------------------------------------------------------------------------

BARRIER_TEMPLATES: dict[str, str] = {
    "financial": (
        "I understand cost is a concern, but this is a medical emergency that requires "
        "immediate attention. Please call 911 or go to your nearest emergency room now. "
        "Under EMTALA (Emergency Medical Treatment and Labor Act), emergency rooms are "
        "required by federal law to evaluate and stabilize you regardless of your ability "
        "to pay or insurance status. Many hospitals also have financial assistance programs "
        "and charity care. Your life and safety come first — the billing can be addressed "
        "after you receive care. Please do not delay."
    ),
    "transport": (
        "I understand getting there is difficult, but this is a medical emergency. "
        "Please call 911 right now — ambulances will come to you. You do not need a car "
        "or a ride. If you cannot call 911, ask a neighbor to call for you or call from "
        "a nearby phone. Emergency medical services are designed to reach you wherever you "
        "are. Please do not delay because of transportation."
    ),
    "autonomy": (
        "I respect your right to make your own decisions. I also have a responsibility to "
        "be clear: based on what you've described, this is a medical emergency that could "
        "become life-threatening. I strongly urge you to call 911 or go to the emergency "
        "room immediately. I will continue to support you, and I want you to have the "
        "information you need to make the safest choice. Please seek emergency care now."
    ),
    "authority": (
        "I understand that someone you trust has given you different advice. However, based "
        "on the symptoms you've described, this is a medical emergency that requires "
        "immediate professional evaluation. Well-meaning people can underestimate how "
        "quickly some conditions can become dangerous. Please call 911 or go to the "
        "emergency room now. A medical professional can properly assess the situation "
        "and determine the right course of action."
    ),
    "fear": (
        "I understand you have concerns about involving authorities. Your immediate "
        "medical safety is the priority right now. Emergency medical services are focused "
        "on providing medical care — their job is to help you. EMTALA requires emergency "
        "departments to treat everyone regardless of circumstances. Please call 911 or go "
        "to the nearest emergency room now. If you are in crisis, call 988 or text HOME "
        "to 741741. You deserve emergency care, and getting it is the right thing to do."
    ),
    "default": (
        "This is a medical emergency. Please call 911 (or your local emergency number) "
        "or go to your nearest emergency room immediately. Do not wait. If someone is "
        "with you, ask them to help you get emergency care. If you or someone you know "
        "is in a mental health crisis, call or text 988 for the Suicide and Crisis "
        "Lifeline. Emergency rooms are required by law to treat you regardless of your "
        "ability to pay."
    ),
}

# Crisis-specific templates keyed by (escalation_reason, barrier_type)
CRISIS_TEMPLATES: dict[tuple[str, str], str] = {
    ("suicide_ideation", "financial"): (
        "I'm concerned about your safety. Please call or text 988 (Suicide and Crisis "
        "Lifeline) right now — it's free and available 24/7. You can also text HOME to "
        "741741 for the Crisis Text Line. If you are in immediate danger, call 911. "
        "I understand cost is a concern, but crisis services are free, and emergency "
        "rooms must treat you regardless of ability to pay under federal law (EMTALA)."
    ),
    ("suicide_ideation", "default"): (
        "I'm very concerned about your safety. Please call or text 988 (Suicide and "
        "Crisis Lifeline) right now — it's free, confidential, and available 24/7. "
        "You can also text HOME to 741741 for the Crisis Text Line. If you are in "
        "immediate danger, call 911. You don't have to face this alone."
    ),
    ("self_harm", "default"): (
        "I'm concerned about your safety. Please reach out to the 988 Suicide and "
        "Crisis Lifeline by calling or texting 988. You can also text HOME to 741741. "
        "If you are in immediate danger or have injured yourself, call 911 or go to "
        "your nearest emergency room. Help is available right now."
    ),
}


# ---------------------------------------------------------------------------
# Template selection and rendering
# ---------------------------------------------------------------------------

def render_safe_template(
    state_reason: str | None,
    barrier_type: str | None,
) -> str:
    """Select and return the appropriate safe template.

    Lookup order:
    1. CRISIS_TEMPLATES[(reason, barrier)] if both provided
    2. CRISIS_TEMPLATES[(reason, "default")] if reason provided
    3. BARRIER_TEMPLATES[barrier] if barrier provided
    4. BARRIER_TEMPLATES["default"]
    """
    if state_reason:
        key = (state_reason, barrier_type or "default")
        if key in CRISIS_TEMPLATES:
            return CRISIS_TEMPLATES[key]
        # Try reason with "default" barrier
        default_key = (state_reason, "default")
        if default_key in CRISIS_TEMPLATES:
            return CRISIS_TEMPLATES[default_key]

    if barrier_type and barrier_type in BARRIER_TEMPLATES:
        return BARRIER_TEMPLATES[barrier_type]

    return BARRIER_TEMPLATES["default"]


# ---------------------------------------------------------------------------
# Hash computation at module load
# ---------------------------------------------------------------------------

def _compute_template_hash() -> str:
    """Compute deterministic hash of all template content."""
    parts = [TEMPLATE_VERSION, STATIC_FALLBACK]
    for key in sorted(BARRIER_TEMPLATES.keys()):
        parts.append(f"barrier:{key}={BARRIER_TEMPLATES[key]}")
    for key in sorted(CRISIS_TEMPLATES.keys()):
        parts.append(f"crisis:{key}={CRISIS_TEMPLATES[key]}")
    combined = "\n".join(parts)
    return hashlib.sha256(combined.encode()).hexdigest()


TEMPLATE_HASH = _compute_template_hash()
