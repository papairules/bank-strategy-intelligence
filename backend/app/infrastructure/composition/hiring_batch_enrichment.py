from collections.abc import Callable
from typing import Any

from backend.app.application.hiring import (
    HiringBatchEnrichmentService,
    HiringEnrichmentPersistenceService,
    HiringReadService,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_enrichment import (
    create_hiring_enrichment_service,
    hiring_enrichment_identity,
)
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


def create_hiring_batch_enrichment_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> HiringBatchEnrichmentService:
    resolved = settings or HiringSettings()
    database = SQLiteDatabase(resolved.sqlite_database_path)
    database.initialize()
    return HiringBatchEnrichmentService(
        HiringReadService(database.unit_of_work),
        create_hiring_enrichment_service(resolved, client_factory=client_factory),
        HiringEnrichmentPersistenceService(database.unit_of_work),
        hiring_enrichment_identity(resolved),
    )
