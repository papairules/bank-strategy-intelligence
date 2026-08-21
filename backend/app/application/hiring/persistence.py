from collections.abc import Callable, Iterable
from typing import Protocol, Self
from uuid import UUID

from backend.app.application.hiring.collection import CollectedJob, CollectionResult
from backend.app.application.hiring.enrichment import HiringEnrichmentResult
from backend.app.application.hiring.observability import CollectionRun
from backend.app.domain.hiring import EmploymentType, JobPosting
from backend.app.domain.intelligence import Evidence


class PersistenceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "persistence_error",
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class JobPostingRepository(Protocol):
    def save(self, posting: JobPosting) -> None: ...

    def get(self, job_id: UUID) -> JobPosting | None: ...

    def get_by_source_identity(
        self,
        organization: str,
        source_job_id: str,
    ) -> JobPosting | None: ...

    def list_all(self) -> list[JobPosting]: ...

    def list_by_organization(self, organization: str) -> list[JobPosting]: ...

    def search(
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

    def count(
        self,
        *,
        organization: str | None,
        country: str | None = None,
        employment_type: EmploymentType | None = None,
        location: str | None = None,
        capability: str | None = None,
        seniority: str | None = None,
    ) -> int: ...


class EvidenceRepository(Protocol):
    def save(self, evidence: Evidence) -> None: ...

    def get(self, evidence_id: UUID) -> Evidence | None: ...

    def list_all(self) -> list[Evidence]: ...


class CollectionRunRepository(Protocol):
    def save(self, run: CollectionRun) -> None: ...

    def get(self, run_id: UUID) -> CollectionRun | None: ...

    def list_recent(self, limit: int = 20) -> list[CollectionRun]: ...

    def list_by_organization(
        self,
        organization: str,
        limit: int = 20,
    ) -> list[CollectionRun]: ...


class HiringEnrichmentRepository(Protocol):
    def save(self, enrichment: HiringEnrichmentResult) -> None: ...

    def get_exact(
        self,
        *,
        job_id: UUID,
        evidence_id: UUID,
        provider: str,
        model: str,
        prompt_schema_version: str,
    ) -> HiringEnrichmentResult | None: ...

    def get_latest(self, job_id: UUID) -> HiringEnrichmentResult | None: ...

    def list_by_job(self, job_id: UUID) -> list[HiringEnrichmentResult]: ...

    def list_by_organization(
        self,
        organization: str,
    ) -> list[HiringEnrichmentResult]: ...

    def exists(
        self,
        *,
        job_id: UUID,
        evidence_id: UUID,
        provider: str,
        model: str,
        prompt_schema_version: str,
    ) -> bool: ...


class HiringPersistenceUnitOfWork(Protocol):
    job_postings: JobPostingRepository
    evidence: EvidenceRepository
    collection_runs: CollectionRunRepository
    enrichments: HiringEnrichmentRepository

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class HiringPersistenceService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], HiringPersistenceUnitOfWork],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def save_collected_jobs(self, jobs: Iterable[CollectedJob]) -> int:
        saved = 0
        with self._unit_of_work_factory() as unit_of_work:
            for collected_job in jobs:
                if (
                    collected_job.posting.evidence_id
                    != collected_job.evidence.evidence_id
                ):
                    raise ValueError(
                        "posting evidence_id must match evidence evidence_id"
                    )
                unit_of_work.evidence.save(collected_job.evidence)
                unit_of_work.job_postings.save(collected_job.posting)
                saved += 1
            unit_of_work.commit()
        return saved

    def save_collection_result(self, result: CollectionResult) -> int:
        saved = 0
        with self._unit_of_work_factory() as unit_of_work:
            for collected_job in result.jobs:
                if (
                    collected_job.posting.evidence_id
                    != collected_job.evidence.evidence_id
                ):
                    raise ValueError(
                        "posting evidence_id must match evidence evidence_id"
                    )
                unit_of_work.evidence.save(collected_job.evidence)
                unit_of_work.job_postings.save(collected_job.posting)
                saved += 1
            unit_of_work.collection_runs.save(
                CollectionRun.from_collection_result(result)
            )
            unit_of_work.commit()
        return saved

    def save_collection_run(self, run: CollectionRun) -> None:
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.collection_runs.save(run)
            unit_of_work.commit()


class HiringEnrichmentPersistenceService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], HiringPersistenceUnitOfWork],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def save(self, enrichment: HiringEnrichmentResult) -> None:
        if any(
            support.evidence_id != enrichment.evidence_id
            for support in enrichment.field_support
        ):
            raise ValueError(
                "enrichment support evidence_id must match enrichment evidence_id"
            )
        with self._unit_of_work_factory() as unit_of_work:
            unit_of_work.enrichments.save(enrichment)
            unit_of_work.commit()

    def has_current(
        self,
        *,
        job_id: UUID,
        evidence_id: UUID,
        provider: str,
        model: str,
        prompt_schema_version: str,
    ) -> bool:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.enrichments.exists(
                job_id=job_id,
                evidence_id=evidence_id,
                provider=provider,
                model=model,
                prompt_schema_version=prompt_schema_version,
            )
