import re


_UNSAFE_CLAIMS = (
    r"\bstrategy is\b",
    r"\bis investing\b",
    r"\bis migrating\b",
    r"\bis transforming\b",
    r"\bplans to\b",
    r"\bhas standardized\b",
)


def contains_unsupported_intent_claim(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.casefold())
    return any(re.search(pattern, normalized) for pattern in _UNSAFE_CLAIMS)
