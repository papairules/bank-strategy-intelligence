import asyncio
import json
from types import SimpleNamespace

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ContentFilterFinishReasonError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
import pytest

from backend.app.application.hiring import (
    EnrichmentFailureCode,
    EnrichmentSeniority,
    HiringCapability,
    HiringEnrichmentError,
    HiringEnrichmentService,
    HiringTheme,
)
from backend.app.infrastructure.llm.openai.hiring_enrichment import (
    GROUNDING_INSTRUCTION,
    OpenAIHiringEnrichmentOutput,
    OpenAIHiringEnrichmentProvider,
    normalize_capabilities,
    normalize_seniority,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_enrichment import (
    create_hiring_enrichment_provider,
    hiring_enrichment_identity,
)
from tests.unit.application.test_hiring_enrichment import posting_and_evidence


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.output, Exception):
            raise self.output
        return SimpleNamespace(
            output_parsed=self.output,
            id="response-1",
            model="gpt-test-version",
            usage=SimpleNamespace(
                model_dump=lambda mode: {"input_tokens": 10, "output_tokens": 5}
            ),
        )


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


def run(value):
    return asyncio.run(value)


def provider_output(**overrides):
    values = {
        "capability_classifications": [
            "Cloud and Platform Engineering",
            "unsupported invented capability",
        ],
        "skills": ["Cloud migration"],
        "technologies": ["Python", "ImaginaryDB"],
        "seniority_level": "VP",
        "is_leadership": True,
        "business_unit": "Risk Technology",
        "hiring_themes": ["cloud modernization", "invented theme"],
        "model_confidence": 0.8,
    }
    values.update(overrides)
    return OpenAIHiringEnrichmentOutput(**values)


def request_model():
    posting, evidence = posting_and_evidence()
    return HiringEnrichmentService._request(posting, evidence)


def test_openai_provider_uses_only_supplied_request_and_canonical_mapping():
    output = provider_output()
    client = FakeClient(output)
    provider = OpenAIHiringEnrichmentProvider(
        api_key="test-key",
        model="gpt-test",
        client_factory=lambda **kwargs: client,
    )
    posting, evidence = posting_and_evidence()
    request = HiringEnrichmentService._request(posting, evidence)

    result = run(provider.enrich(request))

    assert result.output.capability_classifications == [
        HiringCapability.CLOUD_INFRASTRUCTURE
    ]
    assert result.output.seniority_level is EnrichmentSeniority.DIRECTOR
    assert result.output.is_leadership is True
    assert result.output.hiring_themes == [HiringTheme.CLOUD_MODERNIZATION]
    assert result.metadata.provider == "openai"
    assert result.metadata.model == "gpt-test"
    assert result.metadata.prompt_schema_version == "openai-hiring-enrichment-v1"
    call = client.responses.calls[0]
    assert call["text_format"] is OpenAIHiringEnrichmentOutput
    assert "tools" not in call
    assert "do not use web search" in GROUNDING_INSTRUCTION.casefold()
    payload = json.loads(call["input"])
    assert payload["job_id"] == str(posting.job_id)
    assert payload["evidence_id"] == str(evidence.evidence_id)
    assert "source_url" not in payload and "posting_url" not in payload


def test_normalization_omits_unsupported_values_and_maps_vp_conservatively():
    assert normalize_capabilities(["Data and AI", "not-real"]) == [
        HiringCapability.AI_ML
    ]
    assert normalize_seniority("Vice President") is EnrichmentSeniority.DIRECTOR
    assert normalize_seniority("made-up") is EnrichmentSeniority.UNKNOWN
    output = provider_output(seniority_level="manager", is_leadership=True)
    assert output.to_application_output().is_leadership is False


def test_canonical_service_removes_ungrounded_openai_values_and_links_real_evidence():
    client = FakeClient(provider_output())
    provider = OpenAIHiringEnrichmentProvider(
        api_key="test-key",
        model="gpt-test",
        client_factory=lambda **kwargs: client,
    )
    posting, evidence = posting_and_evidence()
    result = run(HiringEnrichmentService(provider, enabled=True).enrich(posting, evidence))

    assert result.technologies == ["Python"]
    assert "ImaginaryDB" not in result.technologies
    assert result.source_content_hash
    assert all(item.evidence_id == evidence.evidence_id for item in result.field_support)


def test_openai_composition_reuses_existing_key_model_and_versioned_identity():
    settings = HiringSettings(
        _env_file=None,
        hiring_llm_provider="openai",
        openai_api_key="test-key",
        openai_model="gpt-test",
    )

    provider = create_hiring_enrichment_provider(
        settings, client_factory=lambda **kwargs: FakeClient(provider_output())
    )
    identity = hiring_enrichment_identity(settings)

    assert isinstance(provider, OpenAIHiringEnrichmentProvider)
    assert identity.provider == "openai"
    assert identity.model == "gpt-test"
    assert identity.prompt_schema_version == "openai-hiring-enrichment-v1"


def status_error(error_type, status_code):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        status_code,
        request=request,
        headers={"x-request-id": "req_safe_test"},
    )
    return error_type(
        "unsafe sk-secret-value Authorization: Bearer secret-token",
        response=response,
        body={"unsafe": "sk-secret-value"},
    )


@pytest.mark.parametrize(
    "sdk_error,expected_code,category,status_code",
    [
        (status_error(BadRequestError, 400), EnrichmentFailureCode.INVALID_REQUEST, "bad_request", 400),
        (status_error(UnprocessableEntityError, 422), EnrichmentFailureCode.INVALID_REQUEST, "unprocessable_entity", 422),
        (status_error(NotFoundError, 404), EnrichmentFailureCode.INVALID_REQUEST, "not_found", 404),
        (status_error(ConflictError, 409), EnrichmentFailureCode.INVALID_REQUEST, "conflict", 409),
        (status_error(InternalServerError, 500), EnrichmentFailureCode.PROVIDER_UNAVAILABLE, "internal_server_error", 500),
        (status_error(RateLimitError, 429), EnrichmentFailureCode.BILLING_QUOTA, "rate_limit", 429),
        (status_error(AuthenticationError, 401), EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION, "authentication", 401),
        (status_error(PermissionDeniedError, 403), EnrichmentFailureCode.PERMISSION_DENIED, "permission_denied", 403),
        (status_error(APIStatusError, 418), EnrichmentFailureCode.INVALID_REQUEST, "api_status_error", 418),
    ],
)
def test_openai_status_errors_retain_only_safe_diagnostics(
    sdk_error, expected_code, category, status_code
):
    provider = OpenAIHiringEnrichmentProvider(
        api_key="test-key",
        model="gpt-test",
        client_factory=lambda **kwargs: FakeClient(sdk_error),
    )

    with pytest.raises(HiringEnrichmentError) as caught:
        run(provider.enrich(request_model()))

    error = caught.value
    assert error.code is expected_code
    assert error.metadata == {
        "error_category": category,
        "exception_type": type(sdk_error).__name__,
        "status_code": status_code,
        "request_id": "req_safe_test",
        "sanitized_message": f"OpenAI returned HTTP {status_code}.",
    }
    assert "secret" not in json.dumps(error.metadata).casefold()


@pytest.mark.parametrize(
    "sdk_error,expected_code,category",
    [
        (
            APIConnectionError(
                message="connection failed with sk-secret-value",
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            ),
            EnrichmentFailureCode.PROVIDER_UNAVAILABLE,
            "connection_error",
        ),
        (
            APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses")),
            EnrichmentFailureCode.TIMEOUT,
            "timeout",
        ),
        (
            ContentFilterFinishReasonError(),
            EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT,
            "structured_output_parsing",
        ),
        (
            RuntimeError("unexpected sk-secret-value"),
            EnrichmentFailureCode.PROVIDER_UNAVAILABLE,
            "unexpected_sdk_error",
        ),
    ],
)
def test_openai_non_status_errors_are_classified_without_raw_messages(
    sdk_error, expected_code, category
):
    provider = OpenAIHiringEnrichmentProvider(
        api_key="test-key",
        model="gpt-test",
        client_factory=lambda **kwargs: FakeClient(sdk_error),
    )

    with pytest.raises(HiringEnrichmentError) as caught:
        run(provider.enrich(request_model()))

    assert caught.value.code is expected_code
    assert caught.value.metadata["error_category"] == category
    assert caught.value.metadata["exception_type"] == type(sdk_error).__name__
    assert "secret" not in json.dumps(caught.value.metadata).casefold()


def test_invalid_parsed_output_has_safe_structured_output_diagnostics():
    provider = OpenAIHiringEnrichmentProvider(
        api_key="test-key",
        model="gpt-test",
        client_factory=lambda **kwargs: FakeClient({"invalid": True}),
    )

    with pytest.raises(HiringEnrichmentError) as caught:
        run(provider.enrich(request_model()))

    assert caught.value.code is EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT
    assert caught.value.metadata["error_category"] == "structured_output_validation"
    assert caught.value.metadata["request_id"] == "response-1"
