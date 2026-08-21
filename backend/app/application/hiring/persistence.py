from collections.abc import Callable, Iterable
from typing import Protocol, Self
from uuid import UUID

from backend.app.application.hiring.collection import CollectedJob, CollectionResult
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence


class JobPostingRepository(Protocol):
    def save(self, posting: JobPosting) -> None: ...

    def get(self, job_id: UUID) -> JobPosting | None: ...

    def get_by_source_identity(
        self,
        organization: str,
        source_job_id: str,
    ) -> JobPosting | None: ...

    def list_all(self) -> list[JobPosting]: ...


class EvidenceRepository(Protocol):
    def save(self, evidence: Evidence) -> None: ...

    def get(self, evidence_id: UUID) -> Evidence | None: ...

    def list_all(self) -> list[Evidence]: ...


class HiringPersistenceUnitOfWork(Protocol):
    job_postings: JobPostingRepository
    evidence: EvidenceRepository

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
        return self.save_collected_jobs(result.jobs)
