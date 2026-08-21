from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.api.dependencies import (
    get_technology_analytics_service,
    get_technology_signal_service,
)
from backend.app.api.v1.technology.schemas import (
    TechnologyAnalyticsResponse,
    TechnologyObservationListResponse,
    TechnologySummaryResponse,
    TechnologySignalsResponse,
)
from backend.app.application.technology import (
    TechnologyAnalyticsService,
    TechnologyCategory,
    TechnologySignalService,
)


router = APIRouter(prefix="/technology", tags=["Technology Intelligence"])
TechnologyService = Annotated[
    TechnologyAnalyticsService,
    Depends(get_technology_analytics_service),
]
SignalService = Annotated[TechnologySignalService, Depends(get_technology_signal_service)]


@router.get(
    "/organizations/{organization}/summary",
    response_model=TechnologySummaryResponse,
)
def get_technology_summary(
    organization: str,
    service: TechnologyService,
) -> TechnologySummaryResponse:
    snapshot = service.analytics(organization).snapshot
    limitation = None
    if snapshot.enriched_jobs < snapshot.total_jobs:
        limitation = (
            "Technology intelligence reflects enriched hiring records only and "
            "must not be interpreted as organization-wide technology strategy."
        )
    return TechnologySummaryResponse(snapshot=snapshot, coverage_limitation=limitation)


@router.get(
    "/organizations/{organization}/analytics",
    response_model=TechnologyAnalyticsResponse,
)
def get_technology_analytics(
    organization: str,
    service: TechnologyService,
) -> TechnologyAnalyticsResponse:
    return TechnologyAnalyticsResponse.model_validate(
        service.analytics(organization).model_dump()
    )


@router.get(
    "/organizations/{organization}/signals",
    response_model=TechnologySignalsResponse,
)
def get_technology_signals(
    organization: str,
    service: SignalService,
) -> TechnologySignalsResponse:
    result = service.generate(organization)
    return TechnologySignalsResponse(
        organization=result.organization,
        generated_at=result.generated_at,
        total_jobs=result.total_jobs,
        enriched_jobs=result.enriched_jobs,
        enrichment_coverage=result.enrichment_coverage,
        technology_observation_count=result.technology_observation_count,
        generated_signal_count=len(result.signals),
        signals=result.signals,
        limitations=result.limitations,
    )


@router.get(
    "/organizations/{organization}/observations",
    response_model=TechnologyObservationListResponse,
)
def list_technology_observations(
    organization: str,
    service: TechnologyService,
    technology: str | None = None,
    category: TechnologyCategory | None = None,
    business_unit: str | None = None,
    location: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TechnologyObservationListResponse:
    items = service.observations(organization)
    if technology:
        needle = technology.casefold()
        items = [item for item in items if needle in item.normalized_technology.casefold()]
    if category:
        items = [item for item in items if item.category == category]
    if business_unit:
        needle = business_unit.casefold()
        items = [item for item in items if item.business_unit and needle in item.business_unit.casefold()]
    if location:
        needle = location.casefold()
        items = [item for item in items if needle in item.location.casefold()]
    total = len(items)
    page = items[offset : offset + limit]
    return TechnologyObservationListResponse(
        items=page,
        total=total,
        limit=limit,
        offset=offset,
        returned_count=len(page),
    )
