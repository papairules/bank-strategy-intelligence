from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_strategy_agent_service
from backend.app.application.agents.strategy_agent import (
    StrategyAgentError,
    StrategyAgentFailureCode,
    StrategyAgentResult,
    StrategyAgentStatus,
    StrategyFinding,
    StrategySupportClass,
    StrategySupportReference,
)
from backend.app.main import app


EVIDENCE_ID = UUID("508eb56f-52dd-54b9-a35f-6e96b3986105")
JOB_ID = UUID("ea62e879-bdcb-5785-8b11-a1755bd7c6ea")


class FakeStrategyAgent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    async def answer(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result


def result(status=StrategyAgentStatus.ANSWERED):
    findings = [] if status == StrategyAgentStatus.INSUFFICIENT_EVIDENCE else [
        StrategyFinding(
            title="Observed analytics demand",
            statement="The available hiring evidence suggests analytics demand within the observed sample.",
            support=[StrategySupportReference(
                reference="strategy_ref_1",
                domain="hiring",
                support_class=StrategySupportClass.DERIVED_SIGNAL,
                tool_name="hiring.get_signals",
                evidence_ids=[EVIDENCE_ID],
                job_ids=[JOB_ID],
                signal_ids=[],
            )],
        )
    ]
    return StrategyAgentResult(
        status=status,
        organization="Wells Fargo",
        question="What does the evidence suggest?",
        executive_summary="The available evidence is limited and observational.",
        findings=findings,
        reliability=.42 if findings else 0,
        limitations=["The observation period is short."],
        tool_calls_used=2,
        provider="vertex_gemini",
        model="gemini-2.5-flash",
        agent_version="strategy-orchestrator-v1",
    )


@pytest.fixture
def client_factory():
    def create(agent):
        app.dependency_overrides[get_strategy_agent_service] = lambda: agent
        return TestClient(app)
    yield create
    app.dependency_overrides.clear()


def test_answered_response_serializes_support_and_invokes_once(client_factory):
    agent = FakeStrategyAgent(result())
    with client_factory(agent) as client:
        response = client.post("/api/v1/agents/strategy/answer", json={"organization": "Wells Fargo", "question": "What does the evidence suggest?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["reliability"] == .42
    assert body["findings"][0]["support"][0]["support_class"] == "derived_signal"
    assert body["findings"][0]["support"][0]["evidence_ids"] == [str(EVIDENCE_ID)]
    assert len(agent.requests) == 1
    assert agent.requests[0].organization == "Wells Fargo"
    assert body["strategic_signals"] == []


def test_optional_time_horizon_reaches_strategy_service(client_factory):
    agent = FakeStrategyAgent(result())
    with client_factory(agent) as client:
        response = client.post(
            "/api/v1/agents/strategy/answer",
            json={
                "organization": "Wells Fargo",
                "question": "What does the evidence suggest?",
                "time_horizon": "12 months",
            },
        )
    assert response.status_code == 200
    assert agent.requests[0].time_horizon == "12 months"


def test_insufficient_evidence_is_successful(client_factory):
    with client_factory(FakeStrategyAgent(result(StrategyAgentStatus.INSUFFICIENT_EVIDENCE))) as client:
        response = client.post("/api/v1/agents/strategy/answer", json={"organization": "Wells Fargo", "question": "Prove a strategy"})
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert response.json()["findings"] == []


def test_organization_scope_mismatch_returns_clear_422(client_factory):
    agent = FakeStrategyAgent(error=StrategyAgentError(
        StrategyAgentFailureCode.ORGANIZATION_SCOPE_MISMATCH,
        "The question targets Goldman Sachs, but the current data scope is Wells Fargo. "
        "Switch the Current Data Scope to Goldman Sachs or ask about Wells Fargo.",
    ))
    with client_factory(agent) as client:
        response = client.post(
            "/api/v1/agents/strategy/answer",
            json={
                "organization": "Wells Fargo",
                "question": "What are Goldman Sachs's AI priorities?",
            },
        )
    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "organization_scope_mismatch",
        "message": "The question targets Goldman Sachs, but the current data scope is Wells Fargo. "
        "Switch the Current Data Scope to Goldman Sachs or ask about Wells Fargo.",
    }


@pytest.mark.parametrize("code,expected", [
    (StrategyAgentFailureCode.DISABLED, 503),
    (StrategyAgentFailureCode.PROVIDER_UNAVAILABLE, 503),
    (StrategyAgentFailureCode.QUOTA, 429),
    (StrategyAgentFailureCode.TIMEOUT, 504),
    (StrategyAgentFailureCode.MALFORMED_PROVIDER_OUTPUT, 502),
    (StrategyAgentFailureCode.REFERENCE_VALIDATION, 502),
    (StrategyAgentFailureCode.CLAIM_VALIDATION, 502),
    (StrategyAgentFailureCode.PROVENANCE_VALIDATION, 502),
])
def test_typed_failures_map_safely(client_factory, code, expected):
    agent = FakeStrategyAgent(error=StrategyAgentError(code, "unsafe detail", metadata={"token": "secret"}))
    with client_factory(agent) as client:
        response = client.post("/api/v1/agents/strategy/answer", json={"organization": "Wells Fargo", "question": "Question"})
    assert response.status_code == expected
    assert response.json()["detail"]["code"] == code.value
    assert "unsafe" not in response.text and "secret" not in response.text


def test_request_forbids_blank_and_server_owned_fields(client_factory):
    agent = FakeStrategyAgent(result())
    with client_factory(agent) as client:
        assert client.post("/api/v1/agents/strategy/answer", json={"organization": "Wells Fargo", "question": " "}).status_code == 422
        response = client.post("/api/v1/agents/strategy/answer", json={"organization": "Wells Fargo", "question": "Question", "provider": "other", "tools": [], "reliability": 1, "evidence_ids": [str(EVIDENCE_ID)]})
    assert response.status_code == 422
    assert agent.requests == []


def test_openapi_and_api_import_boundaries(client_factory):
    with client_factory(FakeStrategyAgent(result())) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/agents/strategy/answer"]["post"]
    assert operation["tags"] == ["Strategy Agent"]
    content = "\n".join(path.read_text().casefold() for path in Path("backend/app/api").rglob("*.py"))
    assert "google.genai" not in content
    assert "vertexgemini" not in content
    assert "sqlite3" not in content


def test_main_import_does_not_construct_strategy_provider(monkeypatch):
    from backend.app.api import dependencies
    dependencies.get_strategy_agent_service.cache_clear()
    called = []
    monkeypatch.setattr(dependencies, "create_strategy_agent_service", lambda: called.append(True))
    assert called == []
