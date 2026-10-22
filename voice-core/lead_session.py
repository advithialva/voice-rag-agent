from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from call_stages import CallStages


@dataclass
class Lead:
    call_id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    company: str | None = None
    product_interest: str | None = None
    requirement: str | None = None
    urgency: str | None = None
    notes: str = ""
    transcript: list[dict[str, Any]] = field(default_factory=list)


class LeadSession:
    def __init__(self, call_id: str) -> None:
        self.lead = Lead(call_id=call_id)
        self.call_stages = CallStages()

    def add_transcript(
        self,
        *,
        role: str,
        text: str,
        timestamp: float | None = None,
        language: str | None = None,
        speaker_id: str | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "role": role,
            "text": text,
        }
        if timestamp is not None:
            entry["timestamp"] = timestamp
        if language:
            entry["language"] = language
        if speaker_id:
            entry["speaker_id"] = speaker_id
        self.lead.transcript.append(entry)
        if role == "user" and text:
            self.call_stages.observe_user_message(text)
            self._update_lead_from_user_text(text)
        elif role == "assistant" and text:
            self.call_stages.observe_assistant_message(text)
        return entry

    def as_dict(self) -> dict[str, Any]:
        return asdict(self.lead)

    def next_missing_field(self) -> str:
        return self.call_stages.next_question(self.lead)

    def apply_translation_update(self, text: str) -> None:
        self._update_lead_from_user_text(text)

    def _update_lead_from_user_text(self, text: str) -> None:
        normalized = " ".join(text.strip().split())
        if not normalized:
            return
        lower = normalized.lower()

        if self.lead.email is None:
            email = _extract_email(normalized)
            if email:
                self.lead.email = email

        if self.lead.phone is None:
            phone = _extract_phone(normalized)
            if phone:
                self.lead.phone = phone

        if self.lead.name is None:
            name = _extract_explicit_name(normalized)
            if name:
                self.lead.name = name
            elif self.call_stages.stage == "name":
                name = _extract_short_name(normalized)
                if name:
                    self.lead.name = name

        if self.lead.company is None:
            company = _extract_company(normalized, lower)
            if company:
                self.lead.company = company

        if self.lead.product_interest is None:
            if self.call_stages.stage == "product" or _looks_like_product_interest(lower):
                self.lead.product_interest = normalized

        if self.lead.requirement is None:
            if self.call_stages.stage == "requirement" or _looks_like_requirement(lower):
                self.lead.requirement = normalized

        if self.lead.urgency is None:
            urgency = _extract_urgency(lower)
            if urgency:
                self.lead.urgency = urgency


def _extract_email(text: str) -> str | None:
    match = re.search(r"[^\s@]+@[^\s@]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


def _extract_phone(text: str) -> str | None:
    digits = re.sub(r"\D", "", text)
    if 10 <= len(digits) <= 15:
        return digits
    return None


def _extract_explicit_name(text: str) -> str | None:
    match = re.search(
        r"\b(?:my name is|my name's|my name it is|my name it's|name is|i am|i'm|this is)\s+([A-Za-z][A-Za-z'\- ]{1,40})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    name = match.group(1).strip().rstrip(".!,")
    tokens = [
        token
        for token in name.split()
        if token.isalpha() and token.lower() not in _NAME_NOISE_TOKENS
    ]
    if not tokens:
        return None
    trimmed = " ".join(tokens[:3])
    return _trim_name(trimmed)


def _extract_short_name(text: str) -> str | None:
    words = text.strip().split()
    if 1 <= len(words) <= 3 and all(word.isalpha() for word in words):
        lower = " ".join(words).lower()
        if lower not in _NAME_STOP_PHRASES and not any(
            word.lower() in _NAME_NOISE_TOKENS for word in words
        ):
            return _trim_name(text)

    return None


def _trim_name(text: str) -> str | None:
    cleaned = " ".join(text.split()).strip("- ")
    return cleaned if cleaned else None


def _extract_company(text: str, lower: str) -> str | None:
    if "company" in lower or "business" in lower or "i am with" in lower:
        match = re.search(
            r"\b(?:company is|company's name is|business is|business name is|we are|we're|my company is|i am with|i'm with)\s+([A-Za-z0-9&'\- ]{2,60})",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().rstrip(".,")
    return None


def _extract_urgency(lower: str) -> str | None:
    for phrase, label in _URGENCY_MAP:
        if phrase in lower:
            return label
    return None


def _looks_like_product_interest(lower: str) -> bool:
    return any(token in lower for token in _PRODUCT_INTENT_TOKENS)


def _looks_like_requirement(lower: str) -> bool:
    return any(token in lower for token in _REQUIREMENT_TOKENS)


_NAME_STOP_PHRASES = {
    "hello",
    "hi",
    "hey",
    "yes",
    "yeah",
    "no",
    "nope",
    "ok",
    "okay",
    "are you there",
    "its from my business",
    "from my business",
    "from my company",
}

_NAME_NOISE_TOKENS = {
    "from",
    "with",
    "adv",
    "child",
    "sir",
    "maam",
    "mr",
    "mrs",
}

_PRODUCT_INTENT_TOKENS = (
    "buy",
    "purchase",
    "interested in",
    "looking for",
    "need",
    "want",
)

_REQUIREMENT_TOKENS = (
    "need",
    "requirement",
    "use case",
    "looking for",
    "we need",
    "we want",
)

_URGENCY_MAP = (
    ("asap", "high"),
    ("urgent", "high"),
    ("immediately", "high"),
    ("this week", "high"),
    ("this month", "medium"),
    ("next week", "medium"),
    ("next month", "medium"),
    ("no rush", "low"),
    ("not urgent", "low"),
)
