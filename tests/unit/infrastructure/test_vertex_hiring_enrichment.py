import asyncio
from types import SimpleNamespace

import pytest

from backend.app.application.hiring import (
    EnrichmentFailureCode,
    HiringEnrichmentError,
    HiringEnrichmentService,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_enrichment import (
    create_hiring_enrichment_service,
)
from backend.app.infrastructure.llm.vertex.hiring_enrichment import (
    GROUNDING_INSTRUCTION,
    VertexGeminiHiringEnrichmentProvider,
)
from tests.unit.application.test_hiring_enrichment import (
    posting_and_evidence,
    valid_output,
)


def run(coroutine):
    return asyncio.run(coroutine)


class FakeModels:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeClient:
    def __init__(self, response) -> None:
        self.models = FakeModels(response)
        self.aio = self
        self.closed = False

    async def aclose(self):
        self.closed = True


def request_model():
    posting, evidence = posting_and_evidence()
    return HiringEnrichmentService._request(posting, evidence)


def test_vertex_provider_uses_lazy_client_and_structured_json_schema():
    response = SimpleNamespace(
        parsed=valid_output().model_dump(mode="json"),
        response_id="vertex-request-1",
        model_version="gemini-version-1",
        usage_metadata={"prompt_token_count": 100, "candidates_token_count": 40},
    )
    client = FakeClient(response)
    factory_calls = []

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return client

    provider = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=2048,
        client_factory=factory,
    )
    assert factory_calls == []

    result = run(provider.enrich(request_model()))

    assert factory_calls == [
        {"vertexai": True, "project": "test-project", "location": "global"}
    ]
    call = client.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert call["config"]["response_mime_type"] == "application/json"
    assert "response_json_schema" in call["config"]
    assert call["config"]["temperature"] == 0.1
    assert call["config"]["max_output_tokens"] == 2048
    assert "Use only the supplied job and evidence text" in call["config"]["system_instruction"]
    assert "outside knowledge" in GROUNDING_INSTRUCTION
    assert result.metadata.provider == "vertex_gemini"
    assert result.metadata.provider_request_id == "vertex-request-1"
    run(provider.close())
    assert client.closed is True


def test_vertex_provider_rejects_malformed_output_and_maps_timeout():
    malformed_client = FakeClient(SimpleNamespace(parsed={"invalid": True}))
    malformed = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=1024,
        client_factory=lambda **kwargs: malformed_client,
    )
    with pytest.raises(HiringEnrichmentError) as malformed_error:
        run(malformed.enrich(request_model()))
    assert malformed_error.value.code is EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT

    timeout_client = FakeClient(TimeoutError())
    timeout = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=1024,
        client_factory=lambda **kwargs: timeout_client,
    )
    with pytest.raises(HiringEnrichmentError) as timeout_error:
        run(timeout.enrich(request_model()))
    assert timeout_error.value.code is EnrichmentFailureCode.TIMEOUT


def test_vertex_configuration_requires_project_without_credentials_in_defaults(
    monkeypatch,
):
    defaults = HiringSettings(_env_file=None)
    assert defaults.hiring_enrichment_enabled is False
    assert defaults.hiring_llm_provider == "vertex_gemini"
    assert defaults.gcp_project is None
    assert defaults.gcp_location == "global"
    assert defaults.gemini_model == "gemini-2.5-flash"
    assert defaults.gemini_temperature == 0.1
    assert defaults.gemini_max_output_tokens == 2048
    assert "credential" not in defaults.model_dump()
    assert "api_key" not in defaults.model_dump()

    monkeypatch.setenv("BSI_HIRING_ENRICHMENT_ENABLED", "true")
    monkeypatch.setenv("BSI_GCP_PROJECT", "environment-project")
    monkeypatch.setenv("BSI_GCP_LOCATION", "us-central1")
    monkeypatch.setenv("BSI_GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("BSI_GEMINI_TEMPERATURE", "0.0")
    monkeypatch.setenv("BSI_GEMINI_MAX_OUTPUT_TOKENS", "4096")
    overridden = HiringSettings(_env_file=None)
    assert overridden.hiring_enrichment_enabled is True
    assert overridden.gcp_project == "environment-project"
    assert overridden.gcp_location == "us-central1"
    assert overridden.gemini_temperature == 0.0
    assert overridden.gemini_max_output_tokens == 4096


def test_composition_and_imports_do_not_initialize_client_or_network():
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        raise AssertionError("client must remain lazy")

    service = create_hiring_enrichment_service(
        HiringSettings(
            hiring_enrichment_enabled=False,
            gcp_project="test-project",
        ),
        client_factory=factory,
    )

    assert isinstance(service, HiringEnrichmentService)
    assert calls == []
