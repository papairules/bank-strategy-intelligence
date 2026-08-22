from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_hiring_agent_service
from backend.app.application.agents.hiring_agent import (
    HiringAgentAnswer,
    HiringAgentError,
    HiringAgentFailureCode,
    HiringAgentStatus,
)
from backend.app.application.agents.hiring_agent.pipeline import HiringEvidence, HiringSignal
from backend.app.main import app


class FakeHiringAgent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    async def answer(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result


def result(status=HiringAgentStatus.ANALYZED):
    signals = [] if status == HiringAgentStatus.INSUFFICIENT_DATA else [
        HiringSignal(
            company_id="WELLS_FARGO",
            business_unit="Corporate and Investment Banking",
            department=None,
            capability="Cloud and Platform Engineering",
            direction="concentration",
            strength=0.6,
            job_count=4,
            senior_role_count=1,
            related_skills=["Kubernetes"],
            related_technologies=["AWS"],
            supporting_job_ids=["REQ1"],
            evidence_date="2026-08-21",
            analysis_period="current active-job snapshot",
            confidence=0.5,
            confidence_breakdown={"classification": 0.2},
        )
    ]
    evidence = [] if status == HiringAgentStatus.INSUFFICIENT_DATA else [
        HiringEvidence(
            evidence_id="HIRE_EV_00001",
            company_id="WELLS_FARGO",
            source_job_id="REQ1",
            job_title="Senior Cloud Engineer",
            business_unit="Corporate and Investment Banking",
            capability="Cloud and Platform Engineering",
            location="New York, NY, US",
            posting_date="2026-08-01",
            source_url="https://example.com/jobs/REQ1",
            statement="Open role: Senior Cloud Engineer; capability: Cloud and Platform Engineering",
        )
    ]
    return HiringAgentAnswer(
        status=status,
        organization="Wells Fargo",
        generated_at="2026-08-22T00:00:00+00:00",
        total_input_jobs=4 if signals else 0,
        unique_jobs=4 if signals else 0,
        enriched_jobs=0,
        failed_enrichments=0,
        hiring_signals=signals,
        evidence=evidence,
        warnings=[] if signals else ["No persisted jobs are available for this organization yet."],
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="hiring-agent-v1",
    )


@pytest.fixture
def client_factory():
    def create(agent):
        app.dependency_overrides[get_hiring_agent_service] = lambda: agent
        return TestClient(app)
    yield create
    app.dependency_overrides.clear()


def test_analyzed_response_serializes_signals_and_evidence(client_factory):
    agent = FakeHiringAgent(result())
    with client_factory(agent) as client:
        response = client.post("/api/v1/agents/hiring/answer", json={"organization": "Wells Fargo"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analyzed"
    assert body["hiring_signals"][0]["capability"] == "Cloud and Platform Engineering"
    assert body["evidence"][0]["source_job_id"] == "REQ1"
    assert len(agent.requests) == 1
    assert agent.requests[0].organization == "Wells Fargo"


def test_insufficient_data_is_successful(client_factory):
    with client_factory(FakeHiringAgent(result(HiringAgentStatus.INSUFFICIENT_DATA))) as client:
        response = client.post("/api/v1/agents/hiring/answer", json={"organization": "Wells Fargo"})
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_data"
    assert response.json()["hiring_signals"] == []


@pytest.mark.parametrize("code,expected", [
    (HiringAgentFailureCode.DISABLED, 503),
    (HiringAgentFailureCode.AUTHENTICATION, 503),
    (HiringAgentFailureCode.PROVIDER_UNAVAILABLE, 503),
    (HiringAgentFailureCode.INVALID_REQUEST, 422),
])
def test_typed_failures_map_safely(client_factory, code, expected):
    agent = FakeHiringAgent(error=HiringAgentError(code, "unsafe detail", metadata={"token": "secret"}))
    with client_factory(agent) as client:
        response = client.post("/api/v1/agents/hiring/answer", json={"organization": "Wells Fargo"})
    assert response.status_code == expected
    assert response.json()["detail"]["code"] == code.value
    assert "unsafe" not in response.text and "secret" not in response.text


def test_request_forbids_blank_organization_and_server_owned_fields(client_factory):
    agent = FakeHiringAgent(result())
    with client_factory(agent) as client:
        assert client.post("/api/v1/agents/hiring/answer", json={"organization": " "}).status_code == 422
        response = client.post(
            "/api/v1/agents/hiring/answer",
            json={"organization": "Wells Fargo", "status": "analyzed", "hiring_signals": []},
        )
    assert response.status_code == 422
    assert agent.requests == []


def test_openapi_and_api_import_boundaries(client_factory):
    with client_factory(FakeHiringAgent(result())) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/agents/hiring/answer"]["post"]
    assert operation["tags"] == ["Hiring Agent"]
    content = "\n".join(path.read_text().casefold() for path in Path("backend/app/api").rglob("*.py"))
    assert "google.genai" not in content
    assert "sqlite3" not in content


def test_main_import_does_not_construct_hiring_agent_provider(monkeypatch):
    from backend.app.api import dependencies
    dependencies.get_hiring_agent_service.cache_clear()
    called = []
    monkeypatch.setattr(dependencies, "create_hiring_agent_service", lambda: called.append(True))
    assert called == []
