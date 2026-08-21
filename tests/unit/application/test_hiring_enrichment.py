import asyncio
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from backend.app.application.hiring import (
    EnrichmentFailureCode,
    EnrichmentField,
    EnrichmentSeniority,
    HiringCapability,
    HiringEnrichmentError,
    HiringEnrichmentService,
    HiringProviderResponse,
    HiringProviderStructuredOutput,
    HiringTheme,
    ProviderFieldSupport,
    ProviderModelMetadata,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType


ENRICHED_AT = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
DESCRIPTION = (
    "Lead cloud migration using Python and Google Cloud. "
    "Manage an engineering team supporting Risk Technology."
)


def run(coroutine):
    return asyncio.run(coroutine)


def posting_and_evidence(*, empty_text: bool = False):
    evidence_id = uuid4()
    posting = JobPosting(
        job_id=uuid4(),
        organization="Example Bank",
        source_job_id="R-1",
        title="Lead Cloud Engineer",
        description=" " if empty_text else DESCRIPTION,
        location="Charlotte, NC",
        country="US",
        posted_date=date(2026, 8, 1),
        source_url="https://careers.example.test/jobs/R-1",
        evidence_id=evidence_id,
    )
    evidence = Evidence(
        evidence_id=evidence_id,
        source_url=posting.source_url,
        source_type=SourceType.CAREER_SITE,
        source_title=posting.title,
        retrieved_at=ENRICHED_AT,
        source_excerpt=None if empty_text else DESCRIPTION,
        raw_reference="synthetic:R-1",
        collector_identity="synthetic-test",
    )
    return posting, evidence


def valid_output() -> HiringProviderStructuredOutput:
    return HiringProviderStructuredOutput(
        capability_classifications=[HiringCapability.CLOUD_INFRASTRUCTURE],
        skills=["Cloud migration", "Team management"],
        technologies=["Python", "Google Cloud"],
        seniority_level=EnrichmentSeniority.LEAD,
        is_leadership=True,
        business_unit="Risk Technology",
        hiring_themes=[HiringTheme.CLOUD_MODERNIZATION],
        model_confidence=0.42,
        field_confidences={
            EnrichmentField.CAPABILITY_CLASSIFICATIONS: 0.9,
            EnrichmentField.SKILLS: 0.8,
            EnrichmentField.TECHNOLOGIES: 0.85,
            EnrichmentField.SENIORITY_LEVEL: 0.8,
            EnrichmentField.IS_LEADERSHIP: 0.75,
            EnrichmentField.BUSINESS_UNIT: 0.7,
            EnrichmentField.HIRING_THEMES: 0.8,
        },
        field_support=[
            ProviderFieldSupport(
                field=EnrichmentField.CAPABILITY_CLASSIFICATIONS,
                value=HiringCapability.CLOUD_INFRASTRUCTURE.value,
                excerpt="cloud migration",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.SKILLS,
                value="Cloud migration",
                excerpt="cloud migration",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.SKILLS,
                value="Team management",
                excerpt="Manage an engineering team",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.TECHNOLOGIES,
                value="Python",
                excerpt="Python",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.TECHNOLOGIES,
                value="Google Cloud",
                excerpt="Google Cloud",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.SENIORITY_LEVEL,
                value="lead",
                excerpt="Lead cloud migration",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.IS_LEADERSHIP,
                value="true",
                excerpt="Manage an engineering team",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.BUSINESS_UNIT,
                value="Risk Technology",
                excerpt="Risk Technology",
            ),
            ProviderFieldSupport(
                field=EnrichmentField.HIRING_THEMES,
                value=HiringTheme.CLOUD_MODERNIZATION.value,
                excerpt="cloud migration",
            ),
        ],
        limitations=["Classification is limited to the supplied posting."],
    )


class FakeHiringEnrichmentProvider:
    def __init__(self, response) -> None:
        self.response = response
        self.requests = []

    async def enrich(self, request):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def provider_response(output=None) -> HiringProviderResponse:
    return HiringProviderResponse(
        output=output or valid_output(),
        metadata=ProviderModelMetadata(
            provider="fake",
            model="fake-model",
            prompt_schema_version="test-v1",
            provider_request_id="request-1",
            model_version="model-version-1",
            usage_metadata={"input_tokens": 100, "output_tokens": 50},
        ),
    )


def test_valid_enrichment_preserves_fields_ids_support_and_provenance():
    posting, evidence = posting_and_evidence()
    provider = FakeHiringEnrichmentProvider(provider_response())
    service = HiringEnrichmentService(
        provider,
        enabled=True,
        clock=lambda: ENRICHED_AT,
    )

    result = run(service.enrich(posting, evidence))

    assert result.job_id == posting.job_id
    assert result.evidence_id == evidence.evidence_id
    assert result.capability_classifications == [
        HiringCapability.CLOUD_INFRASTRUCTURE
    ]
    assert result.skills == ["Cloud migration", "Team management"]
    assert result.technologies == ["Python", "Google Cloud"]
    assert result.seniority_level is EnrichmentSeniority.LEAD
    assert result.is_leadership is True
    assert result.business_unit == "Risk Technology"
    assert result.hiring_themes == [HiringTheme.CLOUD_MODERNIZATION]
    assert all(item.evidence_id == evidence.evidence_id for item in result.field_support)
    assert result.model_metadata.provider == "fake"
    assert result.model_metadata.model == "fake-model"
    assert result.model_metadata.prompt_schema_version == "test-v1"
    assert result.model_metadata.enrichment_timestamp == ENRICHED_AT
    assert result.model_metadata.model_confidence == 0.42
    assert provider.requests[0].existing_normalized_metadata.is_leadership is False


def test_empty_unsupported_fields_are_valid_and_confidence_is_deterministic():
    posting, evidence = posting_and_evidence()
    output = HiringProviderStructuredOutput(
        model_confidence=0.99,
        limitations=["No enrichment fields were sufficiently supported."],
    )
    service = HiringEnrichmentService(
        FakeHiringEnrichmentProvider(provider_response(output)),
        enabled=True,
        clock=lambda: ENRICHED_AT,
    )

    first = run(service.enrich(posting, evidence))
    second = run(service.enrich(posting, evidence))

    assert first.capability_classifications == []
    assert first.skills == []
    assert first.technologies == []
    assert first.seniority_level is EnrichmentSeniority.UNKNOWN
    assert first.business_unit is None
    assert first.hiring_themes == []
    assert first.confidence == 0.6667
    assert 0 <= first.confidence <= 1
    assert first.model_metadata.model_confidence == 0.99
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_malformed_provider_response_and_unsupported_excerpt_are_typed_failures():
    posting, evidence = posting_and_evidence()
    malformed = HiringEnrichmentService(
        FakeHiringEnrichmentProvider({"unexpected": True}),
        enabled=True,
    )

    with pytest.raises(HiringEnrichmentError) as malformed_error:
        run(malformed.enrich(posting, evidence))
    assert malformed_error.value.code is EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT

    output = valid_output()
    output.field_support[0] = ProviderFieldSupport(
        field=EnrichmentField.CAPABILITY_CLASSIFICATIONS,
        value=HiringCapability.CLOUD_INFRASTRUCTURE.value,
        excerpt="not present in supplied evidence",
    )
    unsupported = HiringEnrichmentService(
        FakeHiringEnrichmentProvider(provider_response(output)),
        enabled=True,
    )
    with pytest.raises(HiringEnrichmentError) as support_error:
        run(unsupported.enrich(posting, evidence))
    assert support_error.value.code is EnrichmentFailureCode.VALIDATION_FAILURE


def test_provider_failure_propagates_as_typed_failure():
    posting, evidence = posting_and_evidence()
    expected = HiringEnrichmentError(
        EnrichmentFailureCode.PROVIDER_UNAVAILABLE,
        "Provider unavailable.",
    )
    service = HiringEnrichmentService(
        FakeHiringEnrichmentProvider(expected),
        enabled=True,
    )

    with pytest.raises(HiringEnrichmentError) as error:
        run(service.enrich(posting, evidence))
    assert error.value is expected


def test_empty_evidence_and_disabled_enrichment_fail_before_provider_call():
    posting, evidence = posting_and_evidence(empty_text=True)
    provider = FakeHiringEnrichmentProvider(provider_response())
    enabled = HiringEnrichmentService(provider, enabled=True)
    disabled = HiringEnrichmentService(provider, enabled=False)

    with pytest.raises(HiringEnrichmentError) as empty_error:
        run(enabled.enrich(posting, evidence))
    assert empty_error.value.code is EnrichmentFailureCode.EMPTY_EVIDENCE

    normal_posting, normal_evidence = posting_and_evidence()
    with pytest.raises(HiringEnrichmentError) as disabled_error:
        run(disabled.enrich(normal_posting, normal_evidence))
    assert disabled_error.value.code is EnrichmentFailureCode.DISABLED
    assert provider.requests == []


def test_application_service_is_provider_neutral():
    posting, evidence = posting_and_evidence()
    provider = FakeHiringEnrichmentProvider(provider_response())

    result = run(
        HiringEnrichmentService(provider, enabled=True).enrich(posting, evidence)
    )

    assert result.model_metadata.provider == "fake"
