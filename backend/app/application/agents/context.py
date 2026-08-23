"""Small, in-memory projections used only for agent model context."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_CONTEXT_RECORDS = 10
DEFAULT_EXCERPT_CHARS = 1_200

# These are the fields that can contain source text or repeated support rows.
_TEXT_FIELDS = {
    "description",
    "source_excerpt",
    "evidence_preview",
    "excerpt",
    "support_excerpt",
    "matched_text",
}
_REPEATED_FIELDS = {
    "items",
    "evidence",
    "top_technologies",
    "categories",
    "contributing_records",
    "business_unit_technologies",
    "geography_technologies",
    "seniority_technologies",
    "supporting_job_ids",
    "supporting_evidence_ids",
    "technology_observations",
    "related_hiring_signals",
    "related_technology_signals",
    "hiring_signals",
}


def question_requires_detailed_text(question: str) -> bool:
    """Only explicit source-text queries receive the full stored excerpt."""

    lowered = question.casefold()
    return any(
        phrase in lowered
        for phrase in (
            "full description",
            "job description",
            "quote",
            "quoted",
            "verbatim",
            "exact wording",
            "what does the posting say",
        )
    )


def compact_agent_context(
    value: Any,
    *,
    question: str,
    max_records: int = MAX_CONTEXT_RECORDS,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> Any:
    """Project trusted tool output for a model without mutating the source result."""

    detailed = question_requires_detailed_text(question)

    def visit(item: Any, key: str | None = None) -> Any:
        if isinstance(item, Mapping):
            return {str(child_key): visit(child, str(child_key)) for child_key, child in item.items()}
        if isinstance(item, list):
            limit = max_records if key in _REPEATED_FIELDS else len(item)
            return [visit(child, key) for child in item[:limit]]
        if isinstance(item, str) and key in _TEXT_FIELDS and not detailed and len(item) > excerpt_chars:
            return item[:excerpt_chars].rstrip() + " …"
        return item

    return visit(value)
