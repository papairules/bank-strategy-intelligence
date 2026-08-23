from backend.app.domain.technology_keywords import extract_technologies, find_technology_excerpt


def test_extracts_multiple_unambiguous_technologies():
    text = (
        "Utilizing Java/J2EE technology... Spring Boot, Hibernate, MongoDB... "
        "Apache Kafka, and RabbitMQ; Working Oracle database and DB2 and SQL; "
        "using Node.js, React and Angular; GIT/Bitbucket, Splunk, JUnit, "
        "SonarQube, JIRA, Maven."
    )

    result = extract_technologies(text)

    assert result == sorted(
        [
            "Java",
            "Spring",
            "Hibernate",
            "MongoDB",
            "Kafka",
            "RabbitMQ",
            "Oracle",
            "DB2",
            "SQL",
            "Node.js",
            "React",
            "Angular",
            "Git",
            "Splunk",
            "JUnit",
            "SonarQube",
            "JIRA",
            "Maven",
        ]
    )


def test_matches_are_case_insensitive_for_ordinary_terms():
    assert extract_technologies("Strong PYTHON and kubernetes experience") == ["Kubernetes", "Python"]


def test_does_not_match_substrings_within_other_words():
    assert extract_technologies("The javascript-like syntax of GoLangLanguageX") == ["JavaScript"]
    assert "Golang" not in extract_technologies("GoLangLanguageX is not a real technology")


def test_ambiguous_common_word_technologies_require_capitalization():
    assert extract_technologies("We want you to excel in this role") == []
    assert extract_technologies("Advanced Excel and VBA skills required") == ["Excel", "VBA"]
    assert extract_technologies("this role will spark your career growth") == []
    assert extract_technologies("Experience with Spark and Hadoop") == ["Hadoop", "Spark"]


def test_no_technologies_returns_empty_list():
    assert extract_technologies("General banking operations and customer service.") == []


def test_ignores_none_and_blank_inputs():
    assert extract_technologies(None, "", "Python developer") == ["Python"]


def test_bare_ambiguous_short_tokens_are_not_matched():
    assert extract_technologies("Go to the meeting and review the R code") == []


def test_find_technology_excerpt_returns_a_window_around_the_match():
    excerpt = find_technology_excerpt("Kafka", "We use Apache Kafka for real-time event streaming across services.")
    assert excerpt is not None
    assert "Kafka" in excerpt


def test_find_technology_excerpt_returns_none_when_not_present():
    assert find_technology_excerpt("Kafka", "General banking operations.") is None


def test_find_technology_excerpt_returns_none_for_unknown_technology():
    assert find_technology_excerpt("NotARealTechnology", "Some text with Python in it.") is None
