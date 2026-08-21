from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.dependencies import get_unified_evidence_service
from backend.app.api.v1.evidence.schemas import (
    EvidenceDetailResponse,
    EvidenceRecordsResponse,
    EvidenceSummaryResponse,
)
from backend.app.application.evidence import EvidenceRecordFilters, UnifiedEvidenceService


router = APIRouter(prefix="/evidence", tags=["Evidence & Traceability"])
EvidenceService = Annotated[UnifiedEvidenceService, Depends(get_unified_evidence_service)]


@router.get(
    "/organizations/{organization}/summary",
    response_model=EvidenceSummaryResponse,
)
def get_evidence_summary(
    organization: str,
    service: EvidenceService,
) -> EvidenceSummaryResponse:
    return EvidenceSummaryResponse.model_validate(service.summary(organization).model_dump())


@router.get(
    "/organizations/{organization}/records",
    response_model=EvidenceRecordsResponse,
)
def list_evidence_records(
    organization: str,
    service: EvidenceService,
    search: str | None = None,
    source: str | None = None,
    enriched: bool | None = None,
    technology: str | None = None,
    capability: str | None = None,
    location: str | None = None,
    job_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EvidenceRecordsResponse:
    result = service.list_records(
        organization,
        EvidenceRecordFilters(
            search=search,
            source=source,
            enriched=enriched,
            technology=technology,
            capability=capability,
            location=location,
            job_id=job_id,
            limit=limit,
            offset=offset,
        ),
    )
    return EvidenceRecordsResponse.model_validate(result.model_dump())


@router.get("/{evidence_id}", response_model=EvidenceDetailResponse)
def get_evidence_detail(
    evidence_id: UUID,
    service: EvidenceService,
) -> EvidenceDetailResponse:
    detail = service.get(evidence_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence record not found.",
        )
    return EvidenceDetailResponse.model_validate(detail.model_dump())
