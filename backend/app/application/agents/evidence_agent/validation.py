import re
import unicodedata


def normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def excerpt_is_grounded(excerpt: str, sources: set[str]) -> bool:
    needle = normalized_text(excerpt)
    return bool(needle) and any(needle in normalized_text(source) for source in sources)
