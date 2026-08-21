from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from backend.app.application.hiring.observability import CollectionRun
from backend.app.application.hiring.enrichment import HiringEnrichmentResult
from backend.app.application.hiring.persistence import HiringPersistenceUnitOfWork
from backend.app.domain.hiring import EmploymentType, JobPosting
from backend.app.domain.intelligence import Evidence


class HiringReadServiceProtocol(Protocol):
    def list_jobs(
        self,
        *,
        organization: str | None,
        country: str | None,
        employment_type: EmploymentType | None,
        location: str | None = None,
        capability: str | None = None,
        seniority: str | None = None,
        limit: int,
        offset: int,
    ) -> list[JobPosting]: ...

    def get_job(self, job_id: UUID) -> JobPosting | None: ...

    def get_job_for_organization(
        self,
        organization: str,
        job_id: UUID,
    ) -> JobPosting | None: ...

    def get_evidence(self, evidence_id: UUID) -> Evidence | None: ...

    def list_runs(
        self,
        *,
        organization: str | None,
        limit: int,
    ) -> list[CollectionRun]: ...

    def get_run(self, run_id: UUID) -> CollectionRun | None: ...

    def get_run_for_organization(
        self,
        organization: str,
        run_id: UUID,
    ) -> CollectionRun | None: ...

    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]: ...

    def list_all_jobs(self) -> list[JobPosting]: ...

    def get_enrichment(
        self,
        *,
        job_id: UUID,
        evidence_id: UUID,
        provider: str,
        model: str,
        prompt_schema_version: str,
    ) -> HiringEnrichmentResult | None: ...

    def get_latest_enrichment(
        self,
        job_id: UUID,
    ) -> HiringEnrichmentResult | None: ...

    def list_enrichments(
        self,
        organization: str,
    ) -> list[HiringEnrichmentResult]: ...

    def list_job_enrichments(
        self,
        job_id: UUID,
    ) -> list[HiringEnrichmentResult]: ...

    def count_jobs(
        self,
        *,
        organization: str | None,
        country: str | None = None,
        employment_type: EmploymentType | None = None,
        location: str | None = None,
        capability: str | None = None,
        seniority: str | None = None,
    ) -> int: ...


class HiringReadService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], HiringPersistenceUnitOfWork],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def list_jobs(
        self,
        *,
        organization: str | None,
        country: str | None,
        employment_type: EmploymentType | None,
        location: str | None = None,
        capability: str | None = None,
        seniority: str | None = None,
        limit: int,
        offset: int,
    ) -> list[JobPosting]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.search(
                organization=organization,
                country=country,
                employment_type=employment_type,
                location=location,
                capability=capability,
                seniority=seniority,
                limit=limit,
                offset=offset,
            )

    def get_job(self, job_id: UUID) -> JobPosting | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.get(job_id)

    def get_job_for_organization(
        self,
        organization: str,
        job_id: UUID,
    ) -> JobPosting | None:
        job = self.get_job(job_id)
        return job if job is not None and job.organization == organization else None

    def get_evidence(self, evidence_id: UUID) -> Evidence | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.evidence.get(evidence_id)

    def list_runs(
        self,
        *,
        organization: str | None,
        limit: int,
    ) -> list[CollectionRun]:
        with self._unit_of_work_factory() as unit_of_work:
            if organization is not None:
                return unit_of_work.collection_runs.list_by_organization(
                    organization,
                    limit,
                )
            return unit_of_work.collection_runs.list_recent(limit)

    def get_run(self, run_id: UUID) -> CollectionRun | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.collection_runs.get(run_id)

    def get_run_for_organization(
        self,
        organization: str,
        run_id: UUID,
    ) -> CollectionRun | None:
        run = self.get_run(run_id)
        return run if run is not None and run.organization == organization else None

    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.list_by_organization(organization)

    def list_all_jobs(self) -> list[JobPosting]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.list_all()

    def get_enrichment(
        self,
        *,
        job_id: UUID,
        evidence_id: UUID,
        provider: str,
        model: str,
        prompt_schema_version: str,
    ) -> HiringEnrichmentResult | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.enrichments.get_exact(
                job_id=job_id,
                evidence_id=evidence_id,
                provider=provider,
                model=model,
                prompt_schema_version=prompt_schema_version,
            )

    def get_latest_enrichment(
        self,
        job_id: UUID,
    ) -> HiringEnrichmentResult | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.enrichments.get_latest(job_id)

    def list_enrichments(
        self,
        organization: str,
    ) -> list[HiringEnrichmentResult]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.enrichments.list_by_organization(organization)

    def list_job_enrichments(
        self,
        job_id: UUID,
    ) -> list[HiringEnrichmentResult]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.enrichments.list_by_job(job_id)

    def count_jobs(
        self,
        *,
        organization: str | None,
        country: str | None = None,
        employment_type: EmploymentType | None = None,
        location: str | None = None,
        capability: str | None = None,
        seniority: str | None = None,
    ) -> int:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.count(
                organization=organization,
                country=country,
                employment_type=employment_type,
                location=location,
                capability=capability,
                seniority=seniority,
            )
