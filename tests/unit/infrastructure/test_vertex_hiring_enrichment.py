import asyncio
from types import SimpleNamespace

import pytest
from google.genai.errors import ClientError
from pydantic import ValidationError

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
    VertexHiringEnrichmentOutput,
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


class GuardedResponse:
    def __init__(self, *, parsed, text=None, fail_on_text_access=False, **values):
        self.parsed = parsed
        self._text = text
        self._fail_on_text_access = fail_on_text_access
        self.text_accesses = 0
        for name, value in values.items():
            setattr(self, name, value)

    @property
    def text(self):
        self.text_accesses += 1
        if self._fail_on_text_access:
            raise AssertionError("response.text must not be accessed")
        return self._text


def request_model():
    posting, evidence = posting_and_evidence()
    return HiringEnrichmentService._request(posting, evidence)


def vertex_output():
    return VertexHiringEnrichmentOutput.model_validate(valid_output().model_dump())


def test_vertex_provider_uses_lazy_client_and_structured_json_schema():
    response = GuardedResponse(
        parsed=vertex_output(),
        text="not-json",
        fail_on_text_access=True,
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
        max_output_tokens=4096,
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
    assert call["config"]["response_schema"] is VertexHiringEnrichmentOutput
    assert "response_json_schema" not in call["config"]
    assert call["config"]["temperature"] == 0.1
    assert call["config"]["max_output_tokens"] == 4096
    assert call["config"]["automatic_function_calling"] == {"disable": True}
    assert "tools" not in call["config"]
    assert "Use only the supplied job and evidence text" in call["config"]["system_instruction"]
    assert "outside knowledge" in GROUNDING_INSTRUCTION
    assert "explicitly present in the supplied text" in GROUNDING_INSTRUCTION
    assert "no prose commentary outside the schema" in GROUNDING_INSTRUCTION
    assert result.metadata.provider == "vertex_gemini"
    assert result.metadata.provider_request_id == "vertex-request-1"
    assert result.output.skills == ["Cloud migration"]
    assert result.metadata.prompt_schema_version == "hiring-enrichment-v3"
    assert response.text_accesses == 0
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


def test_vertex_provider_validates_parsed_dict_without_accessing_text():
    response = GuardedResponse(
        parsed=vertex_output().model_dump(mode="json"),
        text="not-json",
        fail_on_text_access=True,
    )
    provider = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=1024,
        client_factory=lambda **kwargs: FakeClient(response),
    )

    result = run(provider.enrich(request_model()))

    assert result.output.seniority_level == vertex_output().seniority_level
    assert response.text_accesses == 0


def test_vertex_provider_uses_valid_json_text_only_when_parsed_is_unavailable():
    response = GuardedResponse(parsed=None, text=vertex_output().model_dump_json())
    provider = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=1024,
        client_factory=lambda **kwargs: FakeClient(response),
    )

    result = run(provider.enrich(request_model()))

    assert result.output.skills == ["Cloud migration"]
    assert response.text_accesses == 1


def test_vertex_provider_reports_safe_invalid_json_response_diagnostics():
    response = GuardedResponse(
        parsed=None,
        text="not-json",
        candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")],
    )
    provider = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=1024,
        client_factory=lambda **kwargs: FakeClient(response),
    )

    with pytest.raises(HiringEnrichmentError) as error:
        run(provider.enrich(request_model()))

    assert error.value.code is EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT
    assert error.value.metadata == {
        "parsed_present": False,
        "parsed_type": None,
        "text_present": True,
        "finish_reason": "MAX_TOKENS",
        "transport_validation_attempted": True,
        "error_type": "invalid_json",
    }
    assert "not-json" not in str(error.value.metadata)


def test_vertex_transport_maps_semantic_values_into_application_provider_output():
    transport = vertex_output()

    application_output = transport.to_application_output()

    assert application_output == valid_output()
    assert set(transport.model_dump()) == {
        "capability_classifications",
        "skills",
        "technologies",
        "seniority_level",
        "is_leadership",
        "business_unit",
        "hiring_themes",
        "model_confidence",
    }


def test_vertex_transport_schema_enforces_compact_collection_limits():
    schema = VertexHiringEnrichmentOutput.model_json_schema()
    assert "maxItems" not in str(schema)
    assert "maxLength" not in str(schema)

    values = vertex_output().model_dump(mode="json")
    values["skills"] = [f"Skill {index}" for index in range(11)]
    with pytest.raises(ValidationError):
        VertexHiringEnrichmentOutput.model_validate(values)
    values = vertex_output().model_dump(mode="json")
    values["model_confidence"] = 1.1
    with pytest.raises(ValidationError):
        VertexHiringEnrichmentOutput.model_validate(values)


def test_vertex_transport_rejects_application_owned_fields_with_safe_diagnostics():
    real_failure_shape = vertex_output().model_dump(mode="json")
    real_failure_shape["job_id"] = "model-injected-id"
    client = FakeClient(SimpleNamespace(parsed=real_failure_shape))
    provider = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=1024,
        client_factory=lambda **kwargs: client,
    )

    with pytest.raises(HiringEnrichmentError) as error:
        run(provider.enrich(request_model()))

    assert error.value.code is EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT
    assert error.value.metadata == {
        "parsed_present": True,
        "parsed_type": "dict",
        "text_present": None,
        "finish_reason": None,
        "transport_validation_attempted": True,
        "error_type": "schema_validation",
        "error_count": 1,
        "validation_errors": [
            {"location": "job_id", "type": "extra_forbidden"}
        ],
    }
    assert "model-injected-id" not in str(error.value.metadata)


@pytest.mark.parametrize(
    ("status_code", "status", "message", "expected_code"),
    [
        (401, "UNAUTHENTICATED", "Authentication required", EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION),
        (403, "PERMISSION_DENIED", "Permission denied", EnrichmentFailureCode.PERMISSION_DENIED),
        (429, "RESOURCE_EXHAUSTED", "Quota exceeded", EnrichmentFailureCode.BILLING_QUOTA),
        (404, "NOT_FOUND", "Model was not found in this location", EnrichmentFailureCode.MODEL_LOCATION),
        (400, "INVALID_ARGUMENT", "Request contains an invalid argument", EnrichmentFailureCode.INVALID_REQUEST),
    ],
)
def test_vertex_client_errors_are_safely_classified(
    status_code,
    status,
    message,
    expected_code,
):
    client_error = ClientError(
        status_code,
        {
            "error": {
                "code": status_code,
                "status": status,
                "message": message,
                "details": [{"reason": status}],
            }
        },
    )
    provider = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=4096,
        client_factory=lambda **kwargs: FakeClient(client_error),
    )

    with pytest.raises(HiringEnrichmentError) as error:
        run(provider.enrich(request_model()))

    assert error.value.code is expected_code
    assert error.value.metadata == {
        "exception_type": "ClientError",
        "http_status_code": status_code,
        "error_status": status,
        "error_message": message,
        "error_reason": status,
    }
    assert "response" not in error.value.metadata
    assert "headers" not in error.value.metadata


def test_vertex_client_error_message_redacts_secret_like_values():
    client_error = ClientError(
        400,
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "Invalid request Authorization: Bearer secret-token access_token=secret-value",
            }
        },
    )
    provider = VertexGeminiHiringEnrichmentProvider(
        project="test-project",
        location="global",
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=4096,
        client_factory=lambda **kwargs: FakeClient(client_error),
    )

    with pytest.raises(HiringEnrichmentError) as error:
        run(provider.enrich(request_model()))

    metadata = str(error.value.metadata)
    assert "secret-token" not in metadata
    assert "secret-value" not in metadata
    assert "[REDACTED]" in metadata


def test_vertex_configuration_requires_project_without_credentials_in_defaults(
    monkeypatch,
):
    for variable in (
        "BSI_HIRING_ENRICHMENT_ENABLED",
        "BSI_HIRING_LLM_PROVIDER",
        "BSI_GCP_PROJECT",
        "BSI_GCP_LOCATION",
        "BSI_GEMINI_MODEL",
        "BSI_GEMINI_TEMPERATURE",
        "BSI_GEMINI_MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(variable, raising=False)
    defaults = HiringSettings(_env_file=None)
    assert defaults.hiring_enrichment_enabled is False
    assert defaults.hiring_llm_provider == "vertex_gemini"
    assert defaults.gcp_project is None
    assert defaults.gcp_location == "global"
    assert defaults.gemini_model == "gemini-2.5-flash"
    assert defaults.gemini_temperature == 0.1
    assert defaults.gemini_max_output_tokens == 4096
    assert "credential" not in defaults.model_dump()
    assert "api_key" not in defaults.model_dump()

    monkeypatch.setenv("BSI_HIRING_ENRICHMENT_ENABLED", "true")
    monkeypatch.setenv("BSI_GCP_PROJECT", "environment-project")
    monkeypatch.setenv("BSI_GCP_LOCATION", "us-central1")
    monkeypatch.setenv("BSI_GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("BSI_GEMINI_TEMPERATURE", "0.0")
    monkeypatch.setenv("BSI_GEMINI_MAX_OUTPUT_TOKENS", "3072")
    overridden = HiringSettings(_env_file=None)
    assert overridden.hiring_enrichment_enabled is True
    assert overridden.gcp_project == "environment-project"
    assert overridden.gcp_location == "us-central1"
    assert overridden.gemini_temperature == 0.0
    assert overridden.gemini_max_output_tokens == 3072


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
