import asyncio
from types import SimpleNamespace

import pytest

from backend.app.application.agents.evidence_agent import (
    EvidenceAgentProviderRequest,
    EvidenceAgentProviderStage,
    EvidenceAgentRequest,
    EvidenceAgentToolSpec,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.evidence_agent import create_evidence_agent_service
from backend.app.infrastructure.llm.vertex.evidence_agent import (
    VertexEvidenceAgentAnswer,
    VertexGeminiEvidenceAgentProvider,
)


class FakeModels:
    def __init__(self, responses): self.responses = list(responses); self.calls = []
    async def generate_content(self, **kwargs): self.calls.append(kwargs); return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses): self.aio = SimpleNamespace(models=FakeModels(responses))


def request(stage, *, results=()):
    return EvidenceAgentProviderRequest(
        stage=stage,
        system_policy="policy",
        request=EvidenceAgentRequest(organization="Bank", question="Question"),
        allowed_tools=[EvidenceAgentToolSpec(name="evidence.search", description="Search", input_schema={"type": "object"})],
        tool_results=list(results),
    )


def test_vertex_provider_is_lazy_and_exposes_only_approved_tool_declarations():
    calls = []
    client = FakeClient([SimpleNamespace(function_calls=[SimpleNamespace(id="x", name="evidence_search", args={"limit": 2})])])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="gemini-2.5-flash", client_factory=lambda **kwargs: calls.append(kwargs) or client)
    assert calls == []
    result = asyncio.run(provider.respond(request(EvidenceAgentProviderStage.PLAN)))
    assert calls == [{"vertexai": True, "project": "project", "location": "global"}]
    assert result.tool_calls[0].name == "evidence.search"
    config = client.aio.models.calls[0]["config"]
    assert config["automatic_function_calling"] == {"disable": True}
    assert [item["name"] for item in config["tools"][0]["function_declarations"]] == ["evidence_search"]


def test_vertex_provider_validates_parsed_structured_answer():
    parsed = VertexEvidenceAgentAnswer(status="insufficient_evidence", answer="Evidence is insufficient.", citations=[], limitations=["Limited sample."], model_confidence=0.2)
    client = FakeClient([SimpleNamespace(parsed=parsed, text="not used")])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: client)
    result = asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER)))
    assert result.answer.status.value == "insufficient_evidence"
    assert client.aio.models.calls[0]["config"]["response_mime_type"] == "application/json"


def test_evidence_agent_configuration_defaults_overrides_and_composition_are_offline(monkeypatch, tmp_path):
    defaults = HiringSettings()
    assert defaults.evidence_agent_enabled is False
    assert defaults.evidence_agent_max_tool_calls == 3
    assert defaults.evidence_agent_max_evidence == 10
    monkeypatch.setenv("BSI_EVIDENCE_AGENT_ENABLED", "true")
    monkeypatch.setenv("BSI_EVIDENCE_AGENT_MAX_TOOL_CALLS", "2")
    monkeypatch.setenv("BSI_EVIDENCE_AGENT_MAX_EVIDENCE", "7")
    settings = HiringSettings(sqlite_database_path=tmp_path / "offline.sqlite3")
    assert settings.evidence_agent_enabled and settings.evidence_agent_max_tool_calls == 2
    initialized = []
    create_evidence_agent_service(settings, client_factory=lambda **kwargs: initialized.append(kwargs))
    assert initialized == []
