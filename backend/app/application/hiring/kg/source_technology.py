from dataclasses import dataclass
from functools import lru_cache
import re


@dataclass(frozen=True)
class SourceTechnologyMatch:
    technology: str
    alias: str
    matched_text: str
    source_field: str


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[str, str, re.Pattern[str]], ...]:
    from backend.app.application.technology.normalization import _ALIASES

    return tuple(
        (alias, technology, re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", re.IGNORECASE))
        for alias, technology in sorted(
            _ALIASES.items(), key=lambda item: (-len(item[0]), item[0])
        )
    )


def extract_source_technologies(
    text: str,
    *,
    source_field: str = "job.description",
) -> list[SourceTechnologyMatch]:
    """Extract only explicitly named technologies from canonical source text."""
    matches: list[SourceTechnologyMatch] = []
    seen: set[str] = set()
    for alias, technology, pattern in _patterns():
        match = pattern.search(text)
        if match is None or technology in seen:
            continue
        seen.add(technology)
        matches.append(
            SourceTechnologyMatch(
                technology=technology,
                alias=alias,
                matched_text=match.group(0),
                source_field=source_field,
            )
        )
    return sorted(matches, key=lambda item: item.technology.casefold())
