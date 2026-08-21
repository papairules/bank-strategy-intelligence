from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.dependencies import get_hiring_read_service
from backend.app.api.v1.hiring.schemas import (
    CollectionRunListResponse,
    JobPostingListResponse,
)
from backend.app.application.hiring import CollectionRun, HiringReadServiceProtocol
from backend.app.domain.hiring import EmploymentType, JobPosting
from backend.app.domain.intelligence import Evidence


router = APIRouter(prefix="/hiring", tags=["Hiring Intelligence"])
ReadService = Annotated[HiringReadServiceProtocol, Depends(get_hiring_read_service)]


@router.get("/jobs", response_model=JobPostingListResponse)
def list_jobs(
    read_service: ReadService,
    organization: str | None = None,
    country: str | None = None,
    employment_type: EmploymentType | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPostingListResponse:
    jobs = read_service.list_jobs(
        organization=organization,
        country=country,
        employment_type=employment_type,
        limit=limit,
        offset=offset,
    )
    return JobPostingListResponse(
        items=jobs,
        limit=limit,
        offset=offset,
        returned_count=len(jobs),
    )


@router.get("/jobs/{job_id}", response_model=JobPosting)
def get_job(job_id: UUID, read_service: ReadService) -> JobPosting:
    job = read_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found.",
        )
    return job


@router.get("/jobs/{job_id}/evidence", response_model=Evidence)
def get_job_evidence(job_id: UUID, read_service: ReadService) -> Evidence:
    job = read_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found.",
        )
    evidence = read_service.get_evidence(job.evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found.",
        )
    return evidence


@router.get("/runs", response_model=CollectionRunListResponse)
def list_runs(
    read_service: ReadService,
    organization: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionRunListResponse:
    runs = read_service.list_runs(organization=organization, limit=limit)
    return CollectionRunListResponse(
        items=runs,
        limit=limit,
        returned_count=len(runs),
    )


@router.get("/runs/{run_id}", response_model=CollectionRun)
def get_run(run_id: UUID, read_service: ReadService) -> CollectionRun:
    collection_run = read_service.get_run(run_id)
    if collection_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection run not found.",
        )
    return collection_run
