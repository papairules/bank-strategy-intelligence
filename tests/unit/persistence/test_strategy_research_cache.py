from datetime import datetime, timezone

import pytest

from backend.app.application.agents.strategy_agent import (
    StrategyAgentResult,
    StrategyAgentStatus,
)
from backend.app.infrastructure.persistence.hiring import (
    SQLiteDatabase,
    SQLiteStrategyResearchCacheRepository,
)


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "strategy_cache.sqlite3")
    database.initialize()
    return database


def result(question: str = "What changed recently?") -> StrategyAgentResult:
    return StrategyAgentResult(
        status=StrategyAgentStatus.ANSWERED,
        organization="Wells Fargo",
        question=question,
        executive_summary="Evidence supports a modernization focus.",
        findings=[],
        reliability=0.72,
        limitations=[],
        tool_calls_used=3,
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
    )


def test_get_returns_none_when_absent(database):
    repository = SQLiteStrategyResearchCacheRepository(database)

    assert repository.get(
        organization="Wells Fargo",
        question_key="what changed recently?",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
    ) is None


def test_save_and_get_round_trips_the_result(database):
    repository = SQLiteStrategyResearchCacheRepository(database)
    generated_at = datetime(2026, 8, 23, 12, tzinfo=timezone.utc).isoformat()

    repository.save(
        organization="Wells Fargo",
        question_key="what changed recently?",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
        generated_at=generated_at,
        result=result(),
    )
    fetched = repository.get(
        organization="Wells Fargo",
        question_key="what changed recently?",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
    )

    assert fetched is not None
    fetched_result, fetched_generated_at = fetched
    assert fetched_result == result()
    assert fetched_generated_at == generated_at


def test_save_overwrites_existing_entry_for_the_same_key(database):
    repository = SQLiteStrategyResearchCacheRepository(database)
    key = dict(
        organization="Wells Fargo",
        question_key="what changed recently?",
        time_horizon="",
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
    )

    repository.save(**key, generated_at="2026-08-01T00:00:00+00:00", result=result("first"))
    repository.save(**key, generated_at="2026-08-23T00:00:00+00:00", result=result("second"))
    fetched_result, fetched_generated_at = repository.get(**key)

    assert fetched_generated_at == "2026-08-23T00:00:00+00:00"
    assert fetched_result.question == "second"


def test_different_time_horizon_is_a_distinct_entry(database):
    repository = SQLiteStrategyResearchCacheRepository(database)
    base_key = dict(
        organization="Wells Fargo",
        question_key="what changed?",
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
    )

    repository.save(**base_key, time_horizon="12 months", generated_at="2026-08-23T00:00:00+00:00", result=result())
    fetched = repository.get(**base_key, time_horizon="24 months")

    assert fetched is None


def test_get_latest_for_organization_returns_none_when_nothing_persisted(database):
    repository = SQLiteStrategyResearchCacheRepository(database)

    assert repository.get_latest_for_organization("Wells Fargo") is None


def test_get_latest_for_organization_ignores_question_and_picks_most_recent(database):
    repository = SQLiteStrategyResearchCacheRepository(database)
    common = dict(organization="Wells Fargo", provider="openai", model="gpt-5.4-mini", agent_version="strategy-langgraph-v1", time_horizon="")

    repository.save(**common, question_key="what changed?", generated_at="2026-08-01T00:00:00+00:00", result=result("older"))
    repository.save(**common, question_key="how are they investing in ai?", generated_at="2026-08-23T00:00:00+00:00", result=result("newer"))

    latest = repository.get_latest_for_organization("Wells Fargo")

    assert latest is not None
    latest_result, latest_generated_at = latest
    assert latest_result.question == "newer"
    assert latest_generated_at == "2026-08-23T00:00:00+00:00"


def test_get_latest_for_organization_does_not_cross_organizations(database):
    repository = SQLiteStrategyResearchCacheRepository(database)
    common = dict(question_key="what changed?", provider="openai", model="gpt-5.4-mini", agent_version="strategy-langgraph-v1", time_horizon="")

    repository.save(**common, organization="BNY", generated_at="2026-08-23T00:00:00+00:00", result=result())

    assert repository.get_latest_for_organization("Wells Fargo") is None
