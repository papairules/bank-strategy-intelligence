from functools import lru_cache

from backend.app.application.hiring import HiringReadService
from backend.app.config import HiringSettings
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


@lru_cache
def get_hiring_read_service() -> HiringReadService:
    settings = HiringSettings()
    database_path = settings.sqlite_database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database = SQLiteDatabase(database_path)
    database.initialize()
    return HiringReadService(database.unit_of_work)
