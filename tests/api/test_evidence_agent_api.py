from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_evidence_agent_service
from backend.app.application.agents.evidence_agent import (
    EvidenceAgentCitation,
    EvidenceAgentError,
    EvidenceAgentFailureCode,
    EvidenceAgentResult,
    EvidenceAgentStatus,
    EvidenceRelationshipType,
)
from backend.app.main import app


EVIDENCE_ID = UUID("508eb56f-52dd-54b9-a35f-6e96b3986105")
JOB_ID = UUID("ea62e879-bdcb-5785-8b11-a1755bd7c6ea")


class FakeEvidenceAgent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.requests = []

    async def answer(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result


def result(status=EvidenceAgentStatus.ANSWERED):
    citations = [] if status == EvidenceAgentStatus.INSUFFICIENT_EVIDENCE else [
        EvidenceAgentCitation(
            evidence_id=EVIDENCE_ID,
            job_id=JOB_ID,
            relationship_type=EvidenceRelationshipType.HIRING_ENRICHMENT,
            source_type="career_site",
        )
    ]
    return EvidenceAgentResult(
        status=status,
        organization="Wells Fargo",
        question="What technologies are supported?",
        answer="SQL and Python are represented in the available enrichment." if citations else "The available evidence is insufficient.",
        citations=citations,
        evidence_records_considered=1,
        tool_calls_used=1,
        reliability=0.4111 if citations else 0.1,
        limitations=["Hiring evidence does not establish corporate intent."],
        provider="vertex_gemini",
        model="gemini-2.5-flash",
        agent_version="evidence-agent-v1",
    )


@pytest.fixture
def client_factory():
    agents = []

    def create(agent):
        agents.append(agent)
        app.dependency_overrides[get_evidence_agent_service] = lambda: agent
        return TestClient(app)

    yield create
    app.dependency_overrides.clear()


def test_answered_response_serializes_citations_reliability_and_scope(client_factory):
    agent = FakeEvidenceAgent(result())
    with client_factory(agent) as client:
        response = client.post("/api/v1/agents/evidence/answer", json={"organization": "Wells Fargo", "question": "What technologies are supported?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["reliability"] == 0.4111
    assert body["citations"][0] == {
        "evidence_id": str(EVIDENCE_ID),
        "job_id": str(JOB_ID),
        "relationship_type": "hiring_enrichment",
        "excerpt": None,
        "source_type": "career_site",
    }
    assert agent.requests[0].organization == "Wells Fargo"


def test_insufficient_evidence_is_a_successful_response(client_factory):
    with client_factory(FakeEvidenceAgent(result(EvidenceAgentStatus.INSUFFICIENT_EVIDENCE))) as client:
        response = client.post("/api/v1/agents/evidence/answer", json={"organization": "Wells Fargo", "question": "Prove a transformation"})
    assert response.status_code == 200
    assert response.json()["status"] == "insufficient_evidence"
    assert response.json()["citations"] == []


@pytest.mark.parametrize("code,expected", [
    (EvidenceAgentFailureCode.DISABLED, 503),
    (EvidenceAgentFailureCode.PROVIDER_UNAVAILABLE, 503),
    (EvidenceAgentFailureCode.AUTHENTICATION, 503),
    (EvidenceAgentFailureCode.PERMISSIONS, 503),
    (EvidenceAgentFailureCode.QUOTA, 429),
    (EvidenceAgentFailureCode.TIMEOUT, 504),
    (EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT, 502),
    (EvidenceAgentFailureCode.CITATION_VALIDATION, 502),
    (EvidenceAgentFailureCode.PROVENANCE_VALIDATION, 502),
])
def test_typed_failures_map_to_safe_http_responses(client_factory, code, expected):
    agent = FakeEvidenceAgent(error=EvidenceAgentError(code, "unsafe internal detail", metadata={"token": "secret"}))
    with client_factory(agent) as client:
        response = client.post("/api/v1/agents/evidence/answer", json={"organization": "Wells Fargo", "question": "Question"})
    assert response.status_code == expected
    assert response.json()["detail"]["code"] == code.value
    assert "unsafe" not in response.text and "secret" not in response.text


def test_request_rejects_blank_unknown_and_unsafe_configuration(client_factory):
    agent = FakeEvidenceAgent(result())
    with client_factory(agent) as client:
        assert client.post("/api/v1/agents/evidence/answer", json={"organization": "Wells Fargo", "question": " "}).status_code == 422
        response = client.post("/api/v1/agents/evidence/answer", json={"organization": "Wells Fargo", "question": "Question", "provider": "other", "model": "other", "tools": ["hiring.get_summary"], "reliability": 1, "evidence_id": str(EVIDENCE_ID)})
    assert response.status_code == 422
    assert agent.requests == []


def test_openapi_and_import_boundaries_are_safe(client_factory):
    with client_factory(FakeEvidenceAgent(result())) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/agents/evidence/answer"]["post"]
    assert operation["tags"] == ["Evidence Agent"]
    content = "\n".join(
        path.read_text().casefold()
        for path in Path("backend/app/api").rglob("*.py")
    )
    assert "google.genai" not in content
    assert "vertexgemini" not in content


def test_main_import_does_not_construct_provider_client(monkeypatch):
    from backend.app.api import dependencies

    dependencies.get_evidence_agent_service.cache_clear()
    called = []
    monkeypatch.setattr(dependencies, "create_evidence_agent_service", lambda: called.append(True))
    assert called == []
