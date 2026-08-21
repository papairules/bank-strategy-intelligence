from dataclasses import dataclass

import httpx

from backend.app.application.hiring import (
    HiringCollectionExecutionService,
    HiringPersistenceService,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo import (
    WellsFargoJobNormalizer,
    WellsFargoSourceAdapter,
)
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


@dataclass
class WellsFargoHiringComposition:
    execution_service: HiringCollectionExecutionService
    database: SQLiteDatabase
    http_client: httpx.AsyncClient

    async def close(self) -> None:
        await self.http_client.aclose()


def create_wells_fargo_hiring_composition(
    settings: HiringSettings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WellsFargoHiringComposition:
    resolved_settings = settings or HiringSettings()
    database_path = resolved_settings.sqlite_database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = SQLiteDatabase(database_path)
    database.initialize()
    client = httpx.AsyncClient(
        timeout=resolved_settings.wells_fargo_request_timeout_seconds,
        transport=transport,
    )
    adapter = WellsFargoSourceAdapter(
        client,
        max_retries=resolved_settings.wells_fargo_retry_count,
    )
    normalizer = WellsFargoJobNormalizer()
    persistence = HiringPersistenceService(database.unit_of_work)
    execution_service = HiringCollectionExecutionService(
        adapter,
        normalizer,
        persistence,
        persistence,
    )
    return WellsFargoHiringComposition(
        execution_service=execution_service,
        database=database,
        http_client=client,
    )
