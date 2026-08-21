from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_cross_domain_strategic_signal_service
from backend.app.api.v1.strategy.schemas import StrategicSignalsResponse
from backend.app.application.strategy import CrossDomainStrategicSignalService


router = APIRouter(prefix="/strategy", tags=["Strategic Intelligence"])
StrategicService = Annotated[
    CrossDomainStrategicSignalService,
    Depends(get_cross_domain_strategic_signal_service),
]


@router.get(
    "/organizations/{organization}/signals",
    response_model=StrategicSignalsResponse,
)
def get_strategic_signals(
    organization: str,
    service: StrategicService,
) -> StrategicSignalsResponse:
    result = service.generate(organization)
    return StrategicSignalsResponse(
        organization=result.organization,
        generated_at=result.generated_at,
        generated_signal_count=len(result.signals),
        coverage_context=result.coverage_context,
        signals=result.signals,
        limitations=result.limitations,
    )
