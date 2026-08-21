import asyncio
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from google.genai import types
from pydantic import ValidationError

from backend.app.application.agents.evidence_agent import (
    EvidenceAgentError,
    EvidenceAgentFailureCode,
    EvidenceAgentProviderRequest,
    EvidenceAgentProviderStage,
    EvidenceAgentRequest,
    EvidenceAgentToolResult,
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
    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception): raise response
        return response


class FakeClient:
    def __init__(self, responses): self.aio = SimpleNamespace(models=FakeModels(responses))


EVIDENCE_ID = UUID("508eb56f-52dd-54b9-a35f-6e96b3986105")
JOB_ID = UUID("ea62e879-bdcb-5785-8b11-a1755bd7c6ea")


def search_result():
    return EvidenceAgentToolResult(
        call_id="search-1",
        name="evidence.search",
        result={
            "items": [{
                "evidence_id": str(EVIDENCE_ID),
                "job_id": str(JOB_ID),
                "organization": "Bank",
                "source_type": "career_site",
                "evidence_preview": "Python and SQL are explicitly required.",
                "enrichment_present": True,
                "related_hiring_signals": [],
                "related_technology_observation_count": 2,
                "related_technology_signals": [],
            }],
            "total": 1,
            "limit": 10,
            "offset": 0,
            "returned_count": 1,
        },
    )


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
    declaration = config["tools"][0]["function_declarations"][0]
    assert "parameters" in declaration and "parameters_json_schema" not in declaration
    assert types.Tool.model_validate(config["tools"][0]).function_declarations


def test_vertex_provider_validates_parsed_structured_answer():
    parsed = VertexEvidenceAgentAnswer(answer="Evidence is insufficient.", citation_references=[], limitations=["Limited sample."])
    client = FakeClient([SimpleNamespace(parsed=parsed, text="not used")])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: client)
    result = asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER)))
    assert result.answer.status.value == "insufficient_evidence"
    assert client.aio.models.calls[0]["config"]["response_mime_type"] == "application/json"
    schema = VertexEvidenceAgentAnswer.model_json_schema()
    assert set(schema["properties"]) == {"answer", "citation_references", "limitations"}
    assert "$defs" not in schema


class TextMustNotBeRead:
    parsed = VertexEvidenceAgentAnswer(
        answer="Evidence is insufficient.",
        citation_references=[],
        limitations=[],
    )
    @property
    def text(self): raise AssertionError("text must not be read when parsed is valid")


@pytest.mark.parametrize("parsed", [
    {"answer": "Insufficient.", "citation_references": [], "limitations": []},
    VertexEvidenceAgentAnswer(answer="Insufficient.", citation_references=[], limitations=[]),
])
def test_answer_uses_valid_parsed_dict_or_model_without_text(parsed):
    response = TextMustNotBeRead()
    response.parsed = parsed
    client = FakeClient([response])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: client)
    result = asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER)))
    assert result.answer.status.value == "insufficient_evidence"


def test_answer_falls_back_to_valid_json_text_and_allows_missing_optional_fields():
    payload = {"answer": "Insufficient.", "citation_references": [], "limitations": []}
    client = FakeClient([SimpleNamespace(parsed=None, text=json.dumps(payload), candidates=[])])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: client)
    result = asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER)))
    assert result.answer.model_confidence is None
    assert result.answer.status.value == "insufficient_evidence"


@pytest.mark.parametrize("response,error_type", [
    (SimpleNamespace(parsed=None, text="not-json", candidates=[]), "JSONDecodeError"),
    (SimpleNamespace(parsed={"status": "answered"}, text=None, candidates=[]), "ValidationError"),
])
def test_malformed_json_and_schema_invalid_answers_are_typed(response, error_type):
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([response]))
    with pytest.raises(EvidenceAgentError) as captured:
        asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER)))
    assert captured.value.code == EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT
    assert captured.value.metadata["validation_stage"] == "answer_response"
    assert captured.value.metadata["validation_error_type"] == error_type


def test_compact_transport_reconstructs_trusted_citation_and_deduplicates_references():
    parsed = VertexEvidenceAgentAnswer(
        answer="Python and SQL are present in the supplied hiring evidence.",
        citation_references=["citation_1", "citation_1"],
        limitations=["Hiring evidence does not establish corporate intent."],
    )
    client = FakeClient([SimpleNamespace(parsed=parsed, candidates=[])])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: client)
    result = asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER, results=[search_result()])))
    assert result.answer.status.value == "answered"
    assert len(result.answer.citations) == 1
    citation = result.answer.citations[0]
    assert citation.evidence_id == EVIDENCE_ID
    assert citation.job_id == JOB_ID
    assert citation.relationship_type.value == "source_evidence"
    assert citation.source_type == "career_site"
    assert citation.excerpt == "Python and SQL are explicitly required."


def test_multiple_valid_citation_relationships_are_application_owned():
    parsed = VertexEvidenceAgentAnswer(
        answer="The source and persisted interpretation both support a bounded answer.",
        citation_references=["citation_1", "citation_2", "citation_3"],
        limitations=[],
    )
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([SimpleNamespace(parsed=parsed, candidates=[])]))
    result = asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER, results=[search_result()])))
    assert [item.relationship_type.value for item in result.answer.citations] == [
        "source_evidence", "hiring_enrichment", "technology_observation"
    ]
    assert all(item.evidence_id == EVIDENCE_ID and item.job_id == JOB_ID for item in result.answer.citations)


def test_unknown_citation_reference_is_rejected_without_accepting_fabricated_identity():
    parsed = VertexEvidenceAgentAnswer(answer="Claim", citation_references=["fabricated"], limitations=[])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([SimpleNamespace(parsed=parsed, candidates=[])]))
    with pytest.raises(EvidenceAgentError) as captured:
        asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER, results=[search_result()])))
    assert captured.value.code == EvidenceAgentFailureCode.CITATION_VALIDATION
    assert captured.value.metadata["validation_stage"] == "citation_reconstruction"


@pytest.mark.parametrize("field,value", [
    ("status", "answered"),
    ("evidence_id", str(EVIDENCE_ID)),
    ("job_id", str(JOB_ID)),
    ("organization", "Bank"),
    ("relationship_type", "source_evidence"),
    ("source_type", "career_site"),
    ("source_url", "https://example.test"),
])
def test_model_cannot_inject_status_identity_or_provenance(field, value):
    payload = {"answer": "Claim", "citation_references": [], "limitations": [], field: value}
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([SimpleNamespace(parsed=payload, candidates=[])]))
    with pytest.raises(EvidenceAgentError) as captured:
        asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER, results=[search_result()])))
    assert captured.value.code == EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT


def test_planning_allows_empty_calls_and_rejects_unknown_or_malformed_calls():
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([SimpleNamespace(function_calls=[], candidates=[])]))
    assert asyncio.run(provider.respond(request(EvidenceAgentProviderStage.PLAN))).tool_calls == []
    for call, code in (
        (SimpleNamespace(name="hiring_get_summary", args={}), EvidenceAgentFailureCode.INVALID_TOOL_REQUEST),
        (SimpleNamespace(name="evidence_search", args={"limit": object()}), EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT),
    ):
        provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda call=call, **kwargs: FakeClient([SimpleNamespace(function_calls=[call], candidates=[])]))
        with pytest.raises(EvidenceAgentError) as captured:
            asyncio.run(provider.respond(request(EvidenceAgentProviderStage.PLAN)))
        assert captured.value.code == code


def test_planning_max_tokens_is_a_typed_malformed_output():
    response = SimpleNamespace(function_calls=[], candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value="MAX_TOKENS"))])
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([response]))
    with pytest.raises(EvidenceAgentError) as captured:
        asyncio.run(provider.respond(request(EvidenceAgentProviderStage.PLAN)))
    assert captured.value.code == EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT
    assert captured.value.metadata["finish_reason"] == "MAX_TOKENS"


def test_answer_max_tokens_retains_safe_finish_reason_diagnostics():
    response = SimpleNamespace(
        parsed=None,
        text="{",
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value="MAX_TOKENS"))],
    )
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([response]))
    with pytest.raises(EvidenceAgentError) as captured:
        asyncio.run(provider.respond(request(EvidenceAgentProviderStage.ANSWER)))
    assert captured.value.code == EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT
    assert captured.value.metadata["finish_reason"] == "MAX_TOKENS"


def test_request_validation_and_provider_errors_are_classified_separately():
    validation = ValidationError.from_exception_data(
        "Config", [{"type": "missing", "loc": ("tools",), "input": {}}]
    )
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([validation]))
    with pytest.raises(EvidenceAgentError) as captured:
        asyncio.run(provider.respond(request(EvidenceAgentProviderStage.PLAN)))
    assert captured.value.code == EvidenceAgentFailureCode.INVALID_PROVIDER_REQUEST
    assert captured.value.metadata["validation_errors"] == [{"path": "tools", "type": "missing"}]

    client_error = type("ClientError", (Exception,), {"status_code": 503})("service unavailable")
    provider = VertexGeminiEvidenceAgentProvider(project="project", location="global", model="model", client_factory=lambda **kwargs: FakeClient([client_error]))
    with pytest.raises(EvidenceAgentError) as captured:
        asyncio.run(provider.respond(request(EvidenceAgentProviderStage.PLAN)))
    assert captured.value.code == EvidenceAgentFailureCode.PROVIDER_UNAVAILABLE


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
