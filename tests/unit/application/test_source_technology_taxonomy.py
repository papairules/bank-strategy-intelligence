from backend.app.application.hiring.kg.source_technology import extract_source_technologies
from backend.app.application.technology.models import TechnologyCategory
from backend.app.application.technology.normalization import (
    categorize_technology,
    normalize_technology,
)


def test_expanded_aliases_normalize_to_stable_technology_names():
    assert normalize_technology(" Apache Kafka ") == "Kafka"
    assert normalize_technology("Postgres") == "PostgreSQL"
    assert normalize_technology("JavaScript") == "JavaScript"
    assert normalize_technology("dotnet") == ".NET"
    assert categorize_technology("Docker") == TechnologyCategory.DEVOPS_INFRASTRUCTURE


def test_java_and_javascript_are_distinct_word_bounded_matches():
    matches = extract_source_technologies(
        "The team uses Java and JavaScript, but not JavaServer Pages."
    )

    assert [match.technology for match in matches] == ["Java", "JavaScript"]
    assert all(match.matched_text.lower() != "javaserver" for match in matches)


def test_ambiguous_terms_require_safe_technology_context():
    matches = extract_source_technologies(
        "Use Apache Spark and Spark SQL for pipelines. The spark of an idea is irrelevant."
    )

    assert [match.technology for match in matches] == ["Spark", "SQL"]
    assert {match.alias for match in matches} == {"sql", "apache spark"}


def test_framework_aliases_do_not_match_plain_ambiguous_words():
    matches = extract_source_technologies(
        "Spring framework, React.js, and AngularJS are used; spring hiring is not a framework claim."
    )

    assert [match.technology for match in matches] == ["Angular", "React", "Spring"]
    assert {match.alias for match in matches} == {"angularjs", "react.js", "spring framework"}


def test_source_match_provenance_is_deterministic():
    text = "Kafka and PostgreSQL support the platform."
    first = extract_source_technologies(text, source_field="job.description")
    second = extract_source_technologies(text, source_field="job.description")

    assert first == second
    assert [(match.technology, match.alias, match.matched_text, match.source_field) for match in first] == [
        ("Kafka", "kafka", "Kafka", "job.description"),
        ("PostgreSQL", "postgresql", "PostgreSQL", "job.description"),
    ]
