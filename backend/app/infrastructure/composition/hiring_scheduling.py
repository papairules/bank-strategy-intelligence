from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx

from backend.app.application.hiring import (
    HiringCollectionScheduler,
    IntervalCadence,
    ScheduledHiringJob,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring import (
    WellsFargoHiringComposition,
    create_wells_fargo_hiring_composition,
)


WELLS_FARGO_SCHEDULED_JOB_ID = "wells-fargo-hiring-collection"


@dataclass
class WellsFargoScheduledHiringComposition:
    hiring: WellsFargoHiringComposition
    scheduler: HiringCollectionScheduler

    async def close(self) -> None:
        await self.scheduler.stop()
        await self.hiring.close()


def create_wells_fargo_scheduled_hiring_composition(
    settings: HiringSettings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], datetime] | None = None,
) -> WellsFargoScheduledHiringComposition:
    resolved_settings = settings or HiringSettings()
    hiring = create_wells_fargo_hiring_composition(
        resolved_settings,
        transport=transport,
    )
    job = ScheduledHiringJob(
        job_id=WELLS_FARGO_SCHEDULED_JOB_ID,
        organization="Wells Fargo",
        enabled=resolved_settings.wells_fargo_schedule_enabled,
        cadence=IntervalCadence(
            seconds=resolved_settings.wells_fargo_schedule_interval_seconds
        ),
        max_pages=resolved_settings.wells_fargo_schedule_max_pages,
        max_records=resolved_settings.wells_fargo_schedule_max_records,
    )
    scheduler_kwargs = {"clock": clock} if clock is not None else {}
    scheduler = HiringCollectionScheduler(
        [job],
        {job.job_id: hiring.execution_service},
        **scheduler_kwargs,
    )
    return WellsFargoScheduledHiringComposition(hiring=hiring, scheduler=scheduler)
