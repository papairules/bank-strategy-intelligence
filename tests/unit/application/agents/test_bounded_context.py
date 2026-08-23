import json

from backend.app.application.agents.context import compact_agent_context


def test_compact_context_bounds_aggregates_and_source_text():
    payload = {
        "top_technologies": [{"technology": str(index)} for index in range(30)],
        "source_excerpt": "x" * 2_000,
    }
    projected = compact_agent_context(payload, question="What technologies are appearing?")

    assert len(projected["top_technologies"]) == 10
    assert len(projected["source_excerpt"]) < 2_000
    assert "description" not in json.dumps(projected)


def test_explicit_source_text_question_keeps_full_excerpt():
    excerpt = "verbatim source text " * 100
    projected = compact_agent_context(
        {"source_excerpt": excerpt},
        question="Quote the exact wording from the full job description.",
    )

    assert projected["source_excerpt"] == excerpt
