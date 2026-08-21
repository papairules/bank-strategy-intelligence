from functools import lru_cache

from fastapi import Depends

from backend.app.application.hiring import HiringDashboardService, HiringReadService
from backend.app.infrastructure.composition.hiring_read import (
    create_hiring_read_service,
)


@lru_cache
def get_hiring_read_service() -> HiringReadService:
    return create_hiring_read_service()


def get_hiring_dashboard_service(
    read_service: HiringReadService = Depends(get_hiring_read_service),
) -> HiringDashboardService:
    return HiringDashboardService(read_service)
