from typing import Protocol
from uuid import UUID

from backend.app.application.agents.models import (
    AgentCollectionContext,
    AgentEnrichmentSummary,
    AgentJobIntelligence,
    AgentJobSearchResult,
    AgentJobSummary,
    CollectionContextInput,
    JobIdInput,
    JobSearchInput,
    OrganizationInput,
)
from backend.app.application.hiring import (
    CollectionRun,
    HiringDashboardService,
    HiringEnrichmentResult,
    HiringOrganizationSummary,
    HiringReadServiceProtocol,
    HiringSignalGenerationResult,
)
from backend.app.domain.hiring import JobPosting


class HiringDashboardBoundary(Protocol):
    def summary(self, organization: str) -> HiringOrganizationSummary: ...
    def signals(self, organization: str) -> HiringSignalGenerationResult: ...


class HiringAgentTools:
    def __init__(
        self,
        read_service: HiringReadServiceProtocol,
        dashboard: HiringDashboardBoundary,
    ) -> None:
        self._read = read_service
        self._dashboard = dashboard

    def get_summary(self, request: OrganizationInput) -> HiringOrganizationSummary:
        return self._dashboard.summary(request.organization)

    def search_jobs(self, request: JobSearchInput) -> AgentJobSearchResult:
        seniority = request.seniority.value if request.seniority else None
        jobs = self._read.list_jobs(
            organization=request.organization,
            country=None,
            employment_type=None,
            location=request.location,
            capability=request.capability,
            seniority=seniority,
            limit=request.limit,
            offset=request.offset,
        )
        total = self._read.count_jobs(
            organization=request.organization,
            location=request.location,
            capability=request.capability,
            seniority=seniority,
        )
        return AgentJobSearchResult(
            organization=request.organization,
            items=[self._job_summary(job) for job in jobs],
            total=total,
            limit=request.limit,
            offset=request.offset,
        )

    def get_job_intelligence(self, request: JobIdInput) -> AgentJobIntelligence:
        job = self._read.get_job_for_organization(
            request.organization,
            request.job_id,
        )
        if job is None:
            return AgentJobIntelligence(
                found=False,
                enrichment=AgentEnrichmentSummary(available=False),
            )
        enrichment = self._read.get_latest_enrichment(job.job_id)
        return AgentJobIntelligence(
            found=True,
            job=self._job_summary(job),
            enrichment=self._enrichment_summary(enrichment),
        )

    def get_signals(self, request: OrganizationInput) -> HiringSignalGenerationResult:
        return self._dashboard.signals(request.organization)

    def get_collection_context(self, request: CollectionContextInput) -> AgentCollectionContext:
        runs = self._read.list_runs(organization=request.organization, limit=request.limit)
        return AgentCollectionContext(
            organization=request.organization,
            runs=runs,
            returned_count=len(runs),
            latest_status=runs[0].status.value if runs else None,
            limitations=[] if runs else ["No collection runs are available for this organization."],
        )

    @staticmethod
    def _job_summary(job: JobPosting) -> AgentJobSummary:
        return AgentJobSummary(
            job_id=job.job_id,
            evidence_id=job.evidence_id,
            organization=job.organization,
            title=job.title,
            location=job.location,
            country=job.country,
            business_unit=job.business_unit,
            capability_classifications=job.capability_classifications,
            seniority_level=job.seniority_level,
            posted_date=job.posted_date,
            employment_type=job.employment_type,
            source_url=job.source_url,
        )

    @staticmethod
    def _enrichment_summary(enrichment: HiringEnrichmentResult | None) -> AgentEnrichmentSummary:
        if enrichment is None:
            return AgentEnrichmentSummary(available=False)
        return AgentEnrichmentSummary(
            available=True,
            provider=enrichment.model_metadata.provider,
            model=enrichment.model_metadata.model,
            prompt_schema_version=enrichment.model_metadata.prompt_schema_version,
            confidence=enrichment.confidence,
            capabilities=enrichment.capability_classifications,
            skills=enrichment.skills,
            technologies=enrichment.technologies,
            seniority=enrichment.seniority_level,
            business_unit=enrichment.business_unit,
            themes=enrichment.hiring_themes,
            limitations=enrichment.limitations,
        )
