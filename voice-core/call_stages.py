from __future__ import annotations

from typing import Protocol


class LeadLike(Protocol):
    name: str | None
    phone: str | None
    email: str | None
    company: str | None
    product_interest: str | None
    requirement: str | None
    urgency: str | None


class CallStages:
    def __init__(self) -> None:
        self._asked: set[str] = set()
        self._stage: str = "greeting"
        self._qualification_enabled = False

    @property
    def stage(self) -> str:
        return self._stage

    @property
    def qualification_enabled(self) -> bool:
        return self._qualification_enabled

    def observe_user_message(self, text: str) -> None:
        if self._qualification_enabled:
            return
        normalized = " ".join(text.lower().split())
        for phrase in _BUYING_SIGNAL_PHRASES:
            if phrase in normalized:
                self._qualification_enabled = True
                self._stage = "qualification"
                return

    def observe_assistant_message(self, text: str) -> None:
        normalized = " ".join(text.lower().split())
        for key, phrases in _ASSISTANT_PROMPT_PHRASES:
            if key in self._asked:
                continue
            if any(phrase in normalized for phrase in phrases):
                self._asked.add(key)
                self._stage = key
                return

    def next_question(self, lead: LeadLike) -> str:
        if not self._qualification_enabled:
            return ""
        for key in ("name", "contact", "product", "requirement", "confirm"):
            if key in self._asked:
                continue

            if key == "name" and not lead.name:
                return self._mark_asked(key, "May I have your name?")

            if key == "contact" and not lead.phone and not lead.email:
                return self._mark_asked(key, "What's the best phone number or email to reach you?")

            if key == "product" and not lead.product_interest:
                return self._mark_asked(key, "Which product or service are you interested in?")

            if key == "requirement" and not lead.requirement:
                return self._mark_asked(key, "What requirement or use case do you have in mind?")

            if key == "confirm":
                if any(
                    [
                        lead.name,
                        lead.phone,
                        lead.email,
                        lead.product_interest,
                        lead.requirement,
                    ]
                ):
                    return self._mark_asked(
                        key,
                        "Thanks — just to confirm, did I capture that correctly?",
                    )
                return self._mark_asked(key, "Is there anything else you'd like to share?")

        return "Thanks — I have everything I need."

    def _mark_asked(self, key: str, question: str) -> str:
        self._asked.add(key)
        self._stage = key
        return question


_BUYING_SIGNAL_PHRASES = (
    "demo",
    "pricing",
    "price",
    "quote",
    "cost",
    "budget",
    "deploy",
    "deployment",
    "implementation",
    "integrat",
    "pilot",
    "poc",
    "proof of concept",
    "contact me",
    "call me",
    "reach out",
    "interested",
    "we need",
    "we want",
    "looking to",
    "buy",
    "purchase",
    "procure",
    "can this work",
    "for my company",
    "for our company",
    "sales team",
    "talk to sales",
    "timeline",
    "how fast",
)

_ASSISTANT_PROMPT_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("name", ("your name", "name?", "name please")),
    (
        "contact",
        (
            "phone number",
            "email",
            "reach you",
            "contact details",
            "best way to reach",
        ),
    ),
    (
        "product",
        (
            "which product",
            "what product",
            "interested in",
        ),
    ),
    (
        "requirement",
        (
            "use case",
            "requirement",
            "what do you need",
        ),
    ),
    (
        "confirm",
        (
            "confirm",
            "did i capture",
        ),
    ),
)
