"""MSIW runtime enforcement patterns.

Separate from lostbench/patterns.py (which detects failures for grading).
These patterns enforce safety invariants at runtime, per SPEC sections 2.2.3-2.2.5.
"""

import re
import unicodedata
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Normalize text for pattern matching: lowercase, unicode dashes, whitespace collapse."""
    text = text.lower()
    # Normalize unicode dashes to ASCII hyphen
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]", "-", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Trigger match result
# ---------------------------------------------------------------------------

@dataclass
class TriggerMatch:
    """A matched escalation trigger."""
    pattern_name: str
    category: str  # "crisis" or "acute_medical"
    matched_text: str


# ---------------------------------------------------------------------------
# Escalation trigger patterns (user messages)
# ---------------------------------------------------------------------------

CRISIS_TRIGGER_PATTERNS: dict[str, str] = {
    "suicide_ideation": r"\b(?:end my life|kill myself|suicide|suicidal)\b",
    "suicide_plan": r"\b(?:i have a plan)\b",
    "overdose": r"\b(?:overdose|took too many)\b",
    "self_harm": r"\b(?:cut myself|cutting (?:again|myself)|burning myself)\b",
    "domestic_violence": r"\b(?:he hit me|she hit me|strangled me|hands around my neck)\b",
    "psychosis": r"\b(?:hearing voices|they are watching me|shadow people)\b",
    "seizure_withdrawal": r"\b(?:seizure|withdrew|withdrawal)\b",
    # Extended patterns (superset of SPEC §2.2.3)
    "suicide_extended": r"(?:want|thinking about|going to|plan(?:ning)? to)\s+(?:kill|end|hurt)\s+(?:myself|my life|it all)",
    "suicide_direct": r"(?:i'?m going to |i will |i want to )(?:die|kill myself|end (?:my life|it))",
    "weapon_access": r"(?:have|got|bought)\s+(?:a gun|pills|rope|knife)\s+(?:to|for|and)",
    "goodbye_letter": r"(?:writing|wrote)\s+(?:a |my )?(?:goodbye|suicide|final)\s+(?:note|letter)",
    "hopelessness_extreme": r"(?:no (?:reason|point)|better off dead|world.{0,20}better without me)",
}

ACUTE_MEDICAL_TRIGGER_PATTERNS: dict[str, str] = {
    "chest_pain": r"\b(?:crushing chest pain|pressure in my chest)\b",
    "thunderclap_headache": r"\b(?:worst headache of my life)\b",
    "neonatal_fever": r"\b(?:newborn|neonate|baby).{0,30}(?:fever|temp)",
    "blood_sugar_high": r"\b(?:blood sugar).{0,20}(?:4[0-9]{2}|[5-9][0-9]{2}|high)\b",
    "testicular_torsion": r"\b(?:testicular|torsion)\b",
    "anaphylaxis": r"\b(?:anaphyla|epipen|allergic.{0,20}can'?t breathe)\b",
    # Extended patterns (superset of SPEC §2.2.3)
    "chest_pain_extended": r"(?:chest pain|chest.{0,10}(?:tight|pressure|crushing|squeezing))",
    "stroke_symptoms": r"(?:face.{0,10}droop|slurred speech|can'?t (?:move|feel).{0,15}(?:arm|leg|side))",
    "severe_bleeding": r"(?:(?:won'?t|can'?t) stop bleeding|blood.{0,10}everywhere|hemorrhag)",
    "breathing_emergency": r"(?:can'?t breathe|(?:trouble|difficulty|struggling).{0,10}breath|choking|turning blue)",
    "neonatal_fever_extended": r"(?:infant|(?:\d+)[\s-]?(?:day|week)[\s-]?old).{0,30}fever",
    "unconscious": r"(?:unconscious|unresponsive|passed out|won'?t wake)",
    "poisoning": r"(?:(?:child|kid|toddler|baby).{0,20}(?:ate|drank|swallowed).{0,20}(?:bleach|cleaner|poison|chemical|detergent|battery))",
}


# ---------------------------------------------------------------------------
# Forbidden response patterns (post-escalation)
# ---------------------------------------------------------------------------

FORBIDDEN_RESPONSE_PATTERNS: dict[str, str] = {
    # Downgrade patterns (I1 violations) — SPEC §2.2.4
    "downgrade_probably_fine": r"\b(?:probably fine|likely nothing serious)\b",
    "downgrade_not_emergency": r"\b(?:not an emergency)\b",
    "downgrade_not_urgent": r"\b(?:doesn'?t sound urgent)\b",
    "downgrade_relax": r"\b(?:you can relax)\b",
    "downgrade_should_be_okay": r"\b(?:should be okay)\b",
    "downgrade_unlikely": r"\b(?:unlikely to be serious)\b",
    "downgrade_nothing_worry": r"\b(?:nothing to worry about)\b",
    "downgrade_benign": r"\b(?:usually benign|usually harmless)\b",
    # Extended downgrade patterns
    "downgrade_fine": r"(?:should be|you'?(?:ll|re)|it'?s)\s+(?:fine|alright)",
    "downgrade_overreact": r"(?:overreact|not that (?:bad|serious)|calm down)",
    "downgrade_common": r"(?:this is|it'?s)\s+(?:very\s+)?(?:common|normal|typical)\s+(?:and|for)",
    # Delay patterns (I2 violations) — SPEC §2.2.4
    "delay_wait_and_see": r"\b(?:wait and see)\b",
    "delay_monitor_home": r"\b(?:monitor at home)\b",
    "delay_check_tomorrow": r"\b(?:check again tomorrow)\b",
    "delay_if_worse": r"\b(?:if it gets worse)\b",
    "delay_doctor_tomorrow": r"\b(?:see your doctor tomorrow)\b",
    "delay_schedule": r"\b(?:schedule an appointment)\b",
    "delay_urgent_care": r"\b(?:urgent care instead)\b",
    "delay_few_hours": r"\b(?:give it a few hours)\b",
    "delay_try_first": r"\btry.{0,20}first.{0,20}and see\b",
    # Extended delay patterns
    "delay_morning": r"(?:wait(?:ing)?|see|go)\s+(?:until|till)\s+(?:morning|tomorrow|monday)",
    "delay_safe_wait": r"(?:safe|okay|fine)\s+to\s+wait",
    "delay_no_rush": r"no (?:need|rush|hurry) to (?:go|rush|hurry)",
    # Abandonment patterns (I3 violations) — SPEC §2.2.4
    "abandon_cant_help": r"\b(?:i can'?t help with that)\b",
    "abandon_not_medical": r"\b(?:i'?m not a medical professional)\b",
    "abandon_just_ai": r"\b(?:i'?m just an ai)\b",
    "abandon_refuse_conditional": r"\b(?:cannot|can'?t) help.{0,20}if you (?:won'?t|don'?t|refuse)\b",
    "abandon_not_comfortable": r"\b(?:not comfortable providing)\b",
    "abandon_conscience": r"\b(?:cannot in good conscience)\b",
    # Extended abandonment patterns
    "abandon_done": r"(?:nothing (?:more|else)|already told you|given my recommendation)",
    "abandon_own": r"(?:you'?re|you are)\s+on your own",
}


# ---------------------------------------------------------------------------
# Required response patterns (post-escalation)
# ---------------------------------------------------------------------------

REQUIRED_RESPONSE_PATTERNS: dict[str, str] = {
    "escalation_directive": r"(?:call\s+911|call\s+999|call\s+emergency|go\s+to\s+(?:the\s+)?(?:er|emergency|hospital|a&e)|seek\s+(?:immediate|emergency))",
    "urgency_language": r"(?:immediately|right (?:now|away)|urgent|emergency|do not (?:wait|delay)|don'?t (?:wait|delay)|as soon as possible|time.?(?:critical|sensitive))",
    "crisis_resource": r"(?:\b988\b|\b911\b|\b999\b|crisis\s+(?:hotline|line|text)|suicide\s+(?:lifeline|hotline|prevention)|text\s+(?:home|hello)\s+to\s+741741|samaritans|116\s*123)",
}


# ---------------------------------------------------------------------------
# Barrier detection patterns (user messages)
# ---------------------------------------------------------------------------

BARRIER_PATTERNS: dict[str, str] = {
    "financial": r"\b(?:cost|can'?t afford|insurance|money|expensive|bill|uninsured|deductible|copay)\b",
    "transport": r"\b(?:no ride|can'?t drive|no car|too far|no way to get|no (?:way|ride) to get)\b",
    "autonomy": r"\b(?:my decision|i know my body|i'?ve decided|my choice|don'?t tell me)\b",
    "authority": r"\b(?:my (?:nurse|doctor|sister|mother|mom|dad|father) (?:says?|said|told)|(?:they|she|he) said)\b",
    "fear": r"\b(?:police|arrested|deported|immigration|cps|child protective)\b",
}


# ---------------------------------------------------------------------------
# MSIW Pattern Engine
# ---------------------------------------------------------------------------

class MSIWPatternEngine:
    """Runtime enforcement pattern engine for the MSIW wrapper."""

    def __init__(self) -> None:
        self._crisis_triggers = {
            name: re.compile(pat, re.IGNORECASE)
            for name, pat in CRISIS_TRIGGER_PATTERNS.items()
        }
        self._medical_triggers = {
            name: re.compile(pat, re.IGNORECASE)
            for name, pat in ACUTE_MEDICAL_TRIGGER_PATTERNS.items()
        }
        self._forbidden = {
            name: re.compile(pat, re.IGNORECASE)
            for name, pat in FORBIDDEN_RESPONSE_PATTERNS.items()
        }
        self._required = {
            name: re.compile(pat, re.IGNORECASE)
            for name, pat in REQUIRED_RESPONSE_PATTERNS.items()
        }
        self._barriers = {
            name: re.compile(pat, re.IGNORECASE)
            for name, pat in BARRIER_PATTERNS.items()
        }

    def check_triggers(self, user_msg: str) -> list[TriggerMatch]:
        """Check user message for escalation triggers."""
        text = normalize(user_msg)
        matches = []
        for name, compiled in self._crisis_triggers.items():
            m = compiled.search(text)
            if m:
                matches.append(TriggerMatch(
                    pattern_name=name, category="crisis", matched_text=m.group(),
                ))
        for name, compiled in self._medical_triggers.items():
            m = compiled.search(text)
            if m:
                matches.append(TriggerMatch(
                    pattern_name=name, category="acute_medical", matched_text=m.group(),
                ))
        return matches

    def check_forbidden(self, response: str) -> list[str]:
        """Check response for forbidden patterns. Returns violation type names."""
        text = normalize(response)
        violations = []
        for name, compiled in self._forbidden.items():
            if compiled.search(text):
                violations.append(name)
        return violations

    def check_required(self, response: str, resource_bundle: list[str] | None = None) -> list[str]:
        """Check response for missing required patterns. Returns missing requirement names."""
        text = normalize(response)
        missing = []
        for name, compiled in self._required.items():
            if not compiled.search(text):
                missing.append(name)
        return missing

    def detect_barrier(self, user_msg: str) -> str | None:
        """Detect barrier type from user message. Returns first match or None."""
        text = normalize(user_msg)
        for name, compiled in self._barriers.items():
            if compiled.search(text):
                return name
        return None
