import re
from collections.abc import Iterable
from typing import Protocol


_UNSAFE_CLAIMS = (
    r"\bstrategy is\b",
    r"\bis investing\b",
    r"\bis migrating\b",
    r"\bis transforming\b",
    r"\bplans to\b",
    r"\bhas standardized\b",
    r"\bhas deployed\b",
    r"\bhas adopted\b",
    r"\benterprise technology strategy\b.{0,80}\b(?:is|focuses|centers|concentrat(?:es|ed))\b",
)

_TECHNOLOGY_SCOPE = re.compile(
    r"\b(?:technology|technologies|technical|ai|artificial intelligence|machine learning|ml)\b"
)
_HIRING_SCOPE = re.compile(r"\b(?:hiring|job postings?|jobs|recruitment)\b")
_CROSS_DOMAIN_ASSERTION = re.compile(
    r"\b(?:hiring|recruitment)\b.{0,120}\b(?:demonstrates?|establishes?|proves?|confirms?)\b"
    r".{0,120}\b(?:technology strategy|technology adoption|technology intent)\b"
)


class SupportReference(Protocol):
    domain: str
    support_class: object
    tool_name: str
    signal_ids: list[object]


def contains_unsupported_intent_claim(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.casefold())
    return any(re.search(pattern, normalized) for pattern in _UNSAFE_CLAIMS)


def contains_unsupported_support_narrowing(
    text: str,
    supports: Iterable[SupportReference],
) -> bool:
    normalized = re.sub(r"\s+", " ", text.casefold())
    trusted = list(supports)
    if _CROSS_DOMAIN_ASSERTION.search(normalized):
        return not any(
            item.tool_name == "strategy.get_signals" and item.signal_ids
            for item in trusted
        )
    if not (_TECHNOLOGY_SCOPE.search(normalized) and _HIRING_SCOPE.search(normalized)):
        return False
    return not any(_supports_technology_scope(item) for item in trusted)


def _supports_technology_scope(reference: SupportReference) -> bool:
    support_class = getattr(reference.support_class, "value", reference.support_class)
    return (
        reference.domain == "technology"
        or support_class == "ai_enrichment"
        or (
            reference.tool_name == "strategy.get_signals"
            and bool(reference.signal_ids)
        )
    )
