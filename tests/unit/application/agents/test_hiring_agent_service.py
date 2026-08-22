import asyncio
from datetime import date
from uuid import uuid4

import pytest

from backend.app.application.agents.hiring_agent import (
    HiringAgentAppRequest,
    HiringAgentAppService,
    HiringAgentError,
    HiringAgentFailureCode,
    HiringAgentStatus,
)
from backend.app.application.agents.hiring_agent.pipeline import FetchResult
from backend.app.domain.hiring import EmploymentType, JobPosting


def make_job_posting(source_job_id: str = "REQ1", title: str = "Senior Cloud Engineer") -> JobPosting:
    return JobPosting(
        job_id=uuid4(),
        organization="Wells Fargo",
        source_job_id=source_job_id,
        title=title,
        description="A sufficiently long description of the role and its responsibilities.",
        location="New York, NY",
        country="US",
        posted_date=date(2026, 8, 1),
        employment_type=EmploymentType.FULL_TIME,
        source_url="https://example.com/jobs/" + source_job_id,
        evidence_id=uuid4(),
    )


class FakeFetcher:
    def fetch(self, job):
        return FetchResult(status="skipped", source_url=job.posting_url)


def build_service(**overrides) -> HiringAgentAppService:
    defaults = dict(
        job_source=lambda organization: [make_job_posting()],
        enabled=True,
        model="gpt-5.4-mini",
        api_key_configured=True,
        use_llm=False,
        fetcher=FakeFetcher(),
    )
    defaults.update(overrides)
    return HiringAgentAppService(**defaults)


def test_disabled_agent_raises():
    service = build_service(enabled=False)
    with pytest.raises(HiringAgentError) as excinfo:
        asyncio.run(service.answer(HiringAgentAppRequest(organization="Wells Fargo")))
    assert excinfo.value.code == HiringAgentFailureCode.DISABLED


def test_missing_credentials_with_llm_enabled_raises():
    service = build_service(use_llm=True, api_key_configured=False)
    with pytest.raises(HiringAgentError) as excinfo:
        asyncio.run(service.answer(HiringAgentAppRequest(organization="Wells Fargo")))
    assert excinfo.value.code == HiringAgentFailureCode.AUTHENTICATION


def test_no_persisted_jobs_returns_insufficient_data():
    service = build_service(job_source=lambda organization: [])
    result = asyncio.run(service.answer(HiringAgentAppRequest(organization="Wells Fargo")))
    assert result.status == HiringAgentStatus.INSUFFICIENT_DATA
    assert result.hiring_signals == []


def test_success_path_produces_signals_and_evidence():
    service = build_service(
        job_source=lambda organization: [
            make_job_posting("REQ1", "Senior Cloud Engineer"),
            make_job_posting("REQ2", "Cloud Platform Engineer"),
        ],
    )
    result = asyncio.run(service.answer(HiringAgentAppRequest(organization="Wells Fargo")))
    assert result.status == HiringAgentStatus.ANALYZED
    assert result.total_input_jobs == 2
    assert result.unique_jobs == 2
    assert result.hiring_signals
    assert result.evidence
    assert result.provider == "openai"
    assert result.agent_version == HiringAgentAppService.AGENT_VERSION


def test_production_path_preserves_description_and_disables_url_fetching():
    from backend.app.application.agents.hiring_agent.service import _raw_job_from_posting

    class ExplodingFetcher:
        def fetch(self, job):
            raise AssertionError("production Hiring Agent must not fetch posting_url")

    posting = make_job_posting()
    service = build_service(job_source=lambda organization: [posting], fetcher=ExplodingFetcher())

    result = asyncio.run(service.answer(HiringAgentAppRequest(organization="Wells Fargo")))

    assert result.status == HiringAgentStatus.ANALYZED
    assert _raw_job_from_posting(posting).description == posting.description
    assert "URL enrichment was disabled." in result.warnings


def test_pipeline_failure_is_wrapped_as_provider_unavailable(monkeypatch):
    import backend.app.application.agents.hiring_agent.service as service_module

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(service_module, "run_hiring_agent_for_jobs", boom)
    service = build_service()
    with pytest.raises(HiringAgentError) as excinfo:
        asyncio.run(service.answer(HiringAgentAppRequest(organization="Wells Fargo")))
    assert excinfo.value.code == HiringAgentFailureCode.PROVIDER_UNAVAILABLE
