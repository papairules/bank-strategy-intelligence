import asyncio
from pathlib import Path

import httpx

from backend.app.application.hiring import CollectionRequest, CollectionStatus
from backend.app.config import HiringSettings
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.adapter import (
    WellsFargoSourceAdapter,
)
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.fixtures import (
    standard_us_full_time,
)
from backend.app.infrastructure.composition.hiring import (
    create_wells_fargo_hiring_composition,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_hiring_settings_defaults_and_environment_overrides(monkeypatch, tmp_path):
    defaults = HiringSettings(_env_file=None)
    assert defaults.sqlite_database_path == Path("data/hiring-intelligence.sqlite3")
    assert defaults.wells_fargo_request_timeout_seconds == 20.0
    assert defaults.wells_fargo_retry_count == 2

    database_path = tmp_path / "override.sqlite3"
    monkeypatch.setenv("BSI_SQLITE_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("BSI_WELLS_FARGO_REQUEST_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("BSI_WELLS_FARGO_RETRY_COUNT", "0")
    overridden = HiringSettings(_env_file=None)
    assert overridden.sqlite_database_path == database_path
    assert overridden.wells_fargo_request_timeout_seconds == 7.5
    assert overridden.wells_fargo_retry_count == 0


def test_wells_fargo_composition_executes_offline_with_mock_transport(tmp_path):
    payload = standard_us_full_time()
    summary = payload["search_summary"]
    detail = payload["job_detail"]
    calls = []

    def handler(request):
        calls.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(200, json={"total": 1, "jobPostings": [summary]})
        return httpx.Response(200, json=detail)

    settings = HiringSettings(
        sqlite_database_path=tmp_path / "wells-fargo.sqlite3",
        wells_fargo_request_timeout_seconds=4.0,
        wells_fargo_retry_count=0,
    )
    composition = create_wells_fargo_hiring_composition(
        settings,
        transport=httpx.MockTransport(handler),
    )

    async def scenario():
        try:
            return await composition.execution_service.execute(
                CollectionRequest(
                    organization="Wells Fargo",
                    max_pages=1,
                    max_records=1,
                )
            )
        finally:
            await composition.close()

    result = run(scenario())

    assert result.status is CollectionStatus.COMPLETED
    assert result.records_persisted == 1
    assert composition.http_client.timeout.read == 4.0
    assert calls[0] == ("POST", WellsFargoSourceAdapter.search_url)
    assert len(calls) == 2
    with composition.database.unit_of_work() as unit_of_work:
        posting = unit_of_work.job_postings.get_by_source_identity(
            "Wells Fargo", "R-100001"
        )
        evidence = unit_of_work.evidence.get(posting.evidence_id)
        audit = unit_of_work.collection_runs.get(result.run_id)
    assert posting.evidence_id == evidence.evidence_id
    assert audit.run_id == result.run_id
