import asyncio
from pathlib import Path

import httpx

from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_scheduling import (
    WELLS_FARGO_SCHEDULED_JOB_ID,
    create_wells_fargo_scheduled_hiring_composition,
)


def test_wells_fargo_schedule_configuration_defaults_and_overrides(
    monkeypatch,
    tmp_path,
):
    defaults = HiringSettings(_env_file=None)
    assert defaults.wells_fargo_schedule_enabled is False
    assert defaults.wells_fargo_schedule_interval_seconds == 86_400
    assert defaults.wells_fargo_schedule_max_pages == 1
    assert defaults.wells_fargo_schedule_max_records == 20

    monkeypatch.setenv("BSI_WELLS_FARGO_SCHEDULE_ENABLED", "true")
    monkeypatch.setenv("BSI_WELLS_FARGO_SCHEDULE_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("BSI_WELLS_FARGO_SCHEDULE_MAX_PAGES", "2")
    monkeypatch.setenv("BSI_WELLS_FARGO_SCHEDULE_MAX_RECORDS", "15")
    monkeypatch.setenv(
        "BSI_SQLITE_DATABASE_PATH",
        str(tmp_path / "scheduled.sqlite3"),
    )
    overridden = HiringSettings(_env_file=None)
    assert overridden.wells_fargo_schedule_enabled is True
    assert overridden.wells_fargo_schedule_interval_seconds == 3600
    assert overridden.wells_fargo_schedule_max_pages == 2
    assert overridden.wells_fargo_schedule_max_records == 15


def test_wells_fargo_scheduled_composition_is_offline_and_not_auto_started(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500)

    settings = HiringSettings(
        sqlite_database_path=tmp_path / "scheduled.sqlite3",
        wells_fargo_schedule_enabled=False,
        wells_fargo_schedule_interval_seconds=7200,
        wells_fargo_schedule_max_pages=1,
        wells_fargo_schedule_max_records=10,
    )
    composition = create_wells_fargo_scheduled_hiring_composition(
        settings,
        transport=httpx.MockTransport(handler),
    )
    job = composition.scheduler.jobs[0]

    assert composition.scheduler.is_running is False
    assert calls == []
    assert job.job_id == WELLS_FARGO_SCHEDULED_JOB_ID
    assert job.organization == "Wells Fargo"
    assert job.enabled is False
    assert job.cadence.seconds == 7200
    assert job.max_pages == 1
    assert job.max_records == 10
    assert settings.sqlite_database_path == Path(tmp_path / "scheduled.sqlite3")
    asyncio.run(composition.close())
