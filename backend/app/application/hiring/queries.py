from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from backend.app.application.hiring.observability import CollectionRun
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
        limit: int,
        offset: int,
    ) -> list[JobPosting]: ...

    def get_job(self, job_id: UUID) -> JobPosting | None: ...

    def get_evidence(self, evidence_id: UUID) -> Evidence | None: ...

    def list_runs(
        self,
        *,
        organization: str | None,
        limit: int,
    ) -> list[CollectionRun]: ...

    def get_run(self, run_id: UUID) -> CollectionRun | None: ...

    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]: ...


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
        limit: int,
        offset: int,
    ) -> list[JobPosting]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.search(
                organization=organization,
                country=country,
                employment_type=employment_type,
                limit=limit,
                offset=offset,
            )

    def get_job(self, job_id: UUID) -> JobPosting | None:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.get(job_id)

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

    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]:
        with self._unit_of_work_factory() as unit_of_work:
            return unit_of_work.job_postings.list_by_organization(organization)
