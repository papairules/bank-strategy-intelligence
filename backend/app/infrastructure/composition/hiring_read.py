from backend.app.application.hiring import HiringReadService
from backend.app.config import HiringSettings
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


def create_hiring_read_service(
    settings: HiringSettings | None = None,
) -> HiringReadService:
    resolved_settings = settings or HiringSettings()
    database_path = resolved_settings.sqlite_database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = SQLiteDatabase(database_path)
    database.initialize()
    return HiringReadService(database.unit_of_work)
