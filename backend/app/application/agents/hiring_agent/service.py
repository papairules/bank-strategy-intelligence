import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.application.agents.hiring_agent.models import (
    HiringAgentAnswer,
    HiringAgentAppRequest,
    HiringAgentError,
    HiringAgentFailureCode,
    HiringAgentStatus,
)
from backend.app.application.agents.hiring_agent.pipeline import (
    CompanyContext,
    HiringAgentOutput,
    JobPageFetcher,
    RawJob,
    normalize_company,
    run_hiring_agent_for_jobs,
)
from backend.app.domain.hiring import JobPosting

logger = logging.getLogger(__name__)


def _raw_job_from_posting(job: JobPosting) -> RawJob:
    return RawJob(
        company=job.organization,
        source_job_id=job.source_job_id,
        title=job.title,
        role_family=job.business_unit,
        city=job.location,
        state=None,
        country=job.country,
        workplace_type=None,
        employment_type=job.employment_type.value if job.employment_type else None,
        first_seen_at=None,
        source_posted_at=job.posted_date.isoformat(),
        posting_url=str(job.source_url),
    )


def _company_context(organization: str) -> CompanyContext:
    company_id = normalize_company(organization).upper() or "ORGANIZATION"
    return CompanyContext(company_id=company_id, canonical_name=organization, aliases=[organization])


def _empty_answer(organization: str, model: str) -> HiringAgentAnswer:
    return HiringAgentAnswer(
        status=HiringAgentStatus.INSUFFICIENT_DATA,
        organization=organization,
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_input_jobs=0,
        unique_jobs=0,
        enriched_jobs=0,
        failed_enrichments=0,
        hiring_signals=[],
        evidence=[],
        warnings=["No persisted jobs are available for this organization yet."],
        provider="openai",
        model=model,
        agent_version=HiringAgentAppService.AGENT_VERSION,
    )


def _to_answer(output: HiringAgentOutput, model: str) -> HiringAgentAnswer:
    status = HiringAgentStatus.ANALYZED if output.hiring_signals else HiringAgentStatus.INSUFFICIENT_DATA
    return HiringAgentAnswer(
        status=status,
        organization=output.company_name,
        generated_at=output.generated_at,
        total_input_jobs=output.total_input_jobs,
        unique_jobs=output.unique_jobs,
        enriched_jobs=output.enriched_jobs,
        failed_enrichments=output.failed_enrichments,
        hiring_signals=output.hiring_signals,
        evidence=output.evidence,
        warnings=output.warnings,
        provider="openai",
        model=model,
        agent_version=HiringAgentAppService.AGENT_VERSION,
    )


class HiringAgentAppService:
    """Async FastAPI boundary for the LLM-assisted hiring intelligence pipeline."""

    AGENT_VERSION = "hiring-agent-v1"

    def __init__(
        self,
        *,
        job_source: Callable[[str], list[JobPosting]],
        enabled: bool = False,
        model: str,
        api_key_configured: bool = True,
        use_llm: bool = True,
        max_jobs: int | None = None,
        workers: int = 6,
        cache_directory: Path = Path("data/hiring_agent_cache/job_pages"),
        client_factory: Callable[[], Any] | None = None,
        fetcher: JobPageFetcher | None = None,
    ) -> None:
        self._job_source = job_source
        self._enabled = enabled
        self._model = model
        self._api_key_configured = api_key_configured
        self._use_llm = use_llm
        self._max_jobs = max_jobs
        self._workers = workers
        self._cache_directory = cache_directory
        self._client_factory = client_factory
        self._fetcher = fetcher

    async def answer(self, request: HiringAgentAppRequest) -> HiringAgentAnswer:
        if not self._enabled:
            raise HiringAgentError(HiringAgentFailureCode.DISABLED, "Hiring Agent is disabled.")
        if self._use_llm and not self._api_key_configured:
            raise HiringAgentError(
                HiringAgentFailureCode.AUTHENTICATION,
                "OpenAI API credentials are not configured.",
            )
        postings = self._job_source(request.organization)
        if not postings:
            return _empty_answer(request.organization, self._model)
        jobs = [_raw_job_from_posting(posting) for posting in postings]
        context = _company_context(request.organization)
        client = self._client_factory() if (self._use_llm and self._client_factory) else None
        logger.info("[hiring_agent] organization=%s jobs=%d", request.organization, len(jobs))
        try:
            output = await asyncio.to_thread(
                run_hiring_agent_for_jobs,
                jobs,
                context,
                client=client,
                fetcher=self._fetcher,
                cache_directory=self._cache_directory,
                max_jobs=self._max_jobs,
                use_llm=self._use_llm,
                workers=self._workers,
                model=self._model,
            )
        except HiringAgentError:
            raise
        except Exception as exc:
            raise HiringAgentError(
                HiringAgentFailureCode.PROVIDER_UNAVAILABLE,
                "Hiring Agent execution failed.",
                metadata={"error_type": type(exc).__name__},
            ) from exc
        return _to_answer(output, self._model)
