from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.dependencies import (
    get_hiring_dashboard_service,
    get_hiring_read_service,
)
from backend.app.api.v1.hiring.schemas import (
    CollectionRunListResponse,
    EnrichmentHistoryResponse,
    EnrichmentResponse,
    EvidenceResponse,
    HiringAnalyticsResponse,
    HiringSignalsResponse,
    JobDetailResponse,
    JobPostingListResponse,
    OrganizationSummaryResponse,
)
from backend.app.application.hiring import (
    CollectionRun,
    HiringDashboardService,
    HiringReadServiceProtocol,
)
from backend.app.domain.hiring import EmploymentType, SeniorityLevel


router = APIRouter(prefix="/hiring", tags=["Hiring Intelligence"])
ReadService = Annotated[HiringReadServiceProtocol, Depends(get_hiring_read_service)]
DashboardService = Annotated[
    HiringDashboardService,
    Depends(get_hiring_dashboard_service),
]


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
    total = read_service.count_jobs(
        organization=organization,
        country=country,
        employment_type=employment_type,
    )
    return JobPostingListResponse(
        items=jobs,
        total=total,
        limit=limit,
        offset=offset,
        returned_count=len(jobs),
    )


@router.get(
    "/organizations/{organization}/summary",
    response_model=OrganizationSummaryResponse,
)
def get_organization_summary(
    organization: str,
    dashboard: DashboardService,
) -> OrganizationSummaryResponse:
    return OrganizationSummaryResponse.model_validate(
        dashboard.summary(organization).model_dump()
    )


@router.get(
    "/organizations/{organization}/jobs",
    response_model=JobPostingListResponse,
)
def list_organization_jobs(
    organization: str,
    read_service: ReadService,
    location: str | None = None,
    capability: str | None = None,
    seniority: SeniorityLevel | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPostingListResponse:
    seniority_value = seniority.value if seniority is not None else None
    jobs = read_service.list_jobs(
        organization=organization,
        country=None,
        employment_type=None,
        location=location,
        capability=capability,
        seniority=seniority_value,
        limit=limit,
        offset=offset,
    )
    total = read_service.count_jobs(
        organization=organization,
        location=location,
        capability=capability,
        seniority=seniority_value,
    )
    return JobPostingListResponse(
        items=jobs,
        total=total,
        limit=limit,
        offset=offset,
        returned_count=len(jobs),
    )


@router.get(
    "/organizations/{organization}/analytics",
    response_model=HiringAnalyticsResponse,
)
def get_organization_analytics(
    organization: str,
    dashboard: DashboardService,
) -> HiringAnalyticsResponse:
    return HiringAnalyticsResponse.model_validate(
        dashboard.analytics(organization).model_dump()
    )


@router.get(
    "/organizations/{organization}/signals",
    response_model=HiringSignalsResponse,
)
def get_organization_signals(
    organization: str,
    dashboard: DashboardService,
) -> HiringSignalsResponse:
    generated = dashboard.signals(organization)
    return HiringSignalsResponse(
        organization=generated.organization,
        generated_at=generated.generated_at,
        items=generated.signals,
        returned_count=len(generated.signals),
    )


@router.get(
    "/organizations/{organization}/collection-runs",
    response_model=CollectionRunListResponse,
)
def list_organization_collection_runs(
    organization: str,
    read_service: ReadService,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionRunListResponse:
    runs = read_service.list_runs(organization=organization, limit=limit)
    return CollectionRunListResponse(
        items=runs,
        limit=limit,
        returned_count=len(runs),
    )


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: UUID, read_service: ReadService) -> JobDetailResponse:
    job = _require_job(job_id, read_service)
    evidence = read_service.get_evidence(job.evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found.",
        )
    return JobDetailResponse(
        job=job,
        evidence=evidence,
        enrichment=read_service.get_latest_enrichment(job_id),
    )


@router.get("/jobs/{job_id}/evidence", response_model=EvidenceResponse)
def get_job_evidence(job_id: UUID, read_service: ReadService) -> EvidenceResponse:
    job = _require_job(job_id, read_service)
    evidence = read_service.get_evidence(job.evidence_id)
    if evidence is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found.",
        )
    return EvidenceResponse.model_validate(evidence)


@router.get("/jobs/{job_id}/enrichment", response_model=EnrichmentResponse)
def get_job_enrichment(job_id: UUID, read_service: ReadService) -> EnrichmentResponse:
    _require_job(job_id, read_service)
    enrichment = read_service.get_latest_enrichment(job_id)
    if enrichment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hiring enrichment not found.",
        )
    return EnrichmentResponse.model_validate(enrichment)


@router.get(
    "/jobs/{job_id}/enrichments",
    response_model=EnrichmentHistoryResponse,
)
def list_job_enrichments(
    job_id: UUID,
    read_service: ReadService,
) -> EnrichmentHistoryResponse:
    _require_job(job_id, read_service)
    enrichments = read_service.list_job_enrichments(job_id)
    return EnrichmentHistoryResponse(
        items=enrichments,
        returned_count=len(enrichments),
    )


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


def _require_job(job_id: UUID, read_service: HiringReadServiceProtocol):
    job = read_service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job posting not found.",
        )
    return job
