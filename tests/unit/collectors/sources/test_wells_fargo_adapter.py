import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from backend.app.application.hiring import CollectionRequest
from backend.app.infrastructure.collectors.hiring.protocols import SourceAdapterError
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.adapter import WellsFargoSourceAdapter
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.fixtures import standard_us_full_time


SEARCH_URL = WellsFargoSourceAdapter.search_url
DETAIL_PATH = "/job/Synthetic_R-100001"
DETAIL_URL = f"{WellsFargoSourceAdapter.detail_base_url}{DETAIL_PATH}"


def run(coro):
    return asyncio.run(coro)


def detail_payload():
    return standard_us_full_time()["job_detail"]


def summary(req_id="R-100001", path=DETAIL_PATH, title="Synthetic Role"):
    return {"title": title, "externalPath": path, "locationsText": "Charlotte, NC", "postedOn": "Posted today", "bulletFields": [req_id]}


def adapter(handler, *, retries=0, sleeps=None):
    async def sleeper(delay):
        if sleeps is not None:
            sleeps.append(delay)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return WellsFargoSourceAdapter(client, max_retries=retries, sleeper=sleeper), client


def test_search_request_and_initial_offset():
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url), request.read()))
        return httpx.Response(200, json={"total": 0, "jobPostings": []})

    async def scenario():
        source, client = adapter(handler)
        try:
            await source.fetch_page(CollectionRequest(organization="Wells Fargo"))
        finally:
            await client.aclose()

    run(scenario())
    assert seen[0][0:2] == ("POST", SEARCH_URL)
    assert httpx.Response(200, content=seen[0][2]).json() == {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}


def test_resumed_offset_and_next_cursor():
    bodies = []

    def handler(request):
        bodies.append(request.read())
        if request.method == "POST":
            return httpx.Response(200, json={"total": 40, "jobPostings": []})

    async def scenario():
        source, client = adapter(handler)
        try:
            page = await source.fetch_page(CollectionRequest(organization="Wells Fargo"), "20")
            return page
        finally:
            await client.aclose()

    page = run(scenario())
    assert httpx.Response(200, content=bodies[0]).json()["offset"] == 20
    assert page.next_cursor is None


def test_successful_multiple_jobs_are_sequential_and_preserved():
    calls = []
    first = summary("R-1", "/job/one")
    second = summary("R-2", "/job/two")

    def handler(request):
        calls.append(str(request.url))
        if request.method == "POST":
            return httpx.Response(200, json={"total": 2, "jobPostings": [first, second]})
        payload = detail_payload()
        payload = {"jobPostingInfo": {**payload["jobPostingInfo"], "jobReqId": "R-1" if request.url.path.endswith("one") else "R-2"}}
        return httpx.Response(200, json=payload, headers={"content-type": "application/json"})

    async def scenario():
        source, client = adapter(handler)
        try:
            return await source.fetch_page(CollectionRequest(organization="Wells Fargo"))
        finally:
            await client.aclose()

    page = run(scenario())
    assert [url for url in calls if "/job/" in url] == [DETAIL_URL.replace("Synthetic_R-100001", "one"), DETAIL_URL.replace("Synthetic_R-100001", "two")]
    assert len(page.records) == 2
    assert page.records[0].payload["search_summary"] == first
    assert page.records[0].payload["job_detail"]["jobPostingInfo"]["jobReqId"] == "R-1"
    assert page.next_cursor is None
    assert page.records[0].provenance_metadata["search_result_position"] == 0


def test_non_final_page_generates_next_offset_cursor():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"total": 2, "jobPostings": [summary()]})
        return httpx.Response(200, json=detail_payload())

    async def scenario():
        source, client = adapter(handler)
        try:
            return await source.fetch_page(CollectionRequest(organization="Wells Fargo"))
        finally:
            await client.aclose()

    assert run(scenario()).next_cursor == "1"


def test_failed_detail_becomes_source_issue_and_other_job_survives():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"total": 2, "jobPostings": [summary("R-1", "/job/bad"), summary("R-2", "/job/good")]})
        if request.url.path.endswith("bad"):
            return httpx.Response(403, json={"error": "blocked"})
        payload = detail_payload()
        payload["jobPostingInfo"]["jobReqId"] = "R-2"
        return httpx.Response(200, json=payload)

    async def scenario():
        source, client = adapter(handler)
        try:
            return await source.fetch_page(CollectionRequest(organization="Wells Fargo"))
        finally:
            await client.aclose()

    page = run(scenario())
    assert len(page.records) == 1
    assert len(page.source_issues) == 1
    issue = page.source_issues[0]
    assert issue.code == "forbidden"
    assert issue.source_record_id == "R-1"
    assert issue.record_position == 0
    assert issue.metadata["external_path"] == "/job/bad"
    assert issue.metadata["http_status"] == 403


def test_malformed_detail_json_becomes_parse_issue():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"total": 1, "jobPostings": [summary()]})
        return httpx.Response(200, text="not-json")

    async def scenario():
        source, client = adapter(handler)
        try:
            return await source.fetch_page(CollectionRequest(organization="Wells Fargo"))
        finally:
            await client.aclose()

    issue = run(scenario()).source_issues[0]
    assert issue.code == "malformed_detail_json"
    assert issue.stage.value == "parse"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retryable_statuses_retry_and_exhaust(status):
    attempts = []
    sleeps = []

    def handler(request):
        attempts.append(1)
        return httpx.Response(status, headers={"Retry-After": "3"})

    async def scenario():
        source, client = adapter(handler, retries=2, sleeps=sleeps)
        try:
            with pytest.raises(SourceAdapterError) as exc:
                await source.fetch_page(CollectionRequest(organization="Wells Fargo"))
            return exc.value
        finally:
            await client.aclose()

    error = run(scenario())
    assert len(attempts) == 3
    assert sleeps == [3.0, 3.0]
    assert error.metadata["http_status"] == status


def test_malformed_and_unexpected_search_responses_are_typed_errors():
    responses = [httpx.Response(200, text="not-json"), httpx.Response(200, json={"total": 1})]

    async def scenario():
        def handler(request):
            return responses.pop(0)

        source, client = adapter(handler)
        try:
            errors = []
            for _ in range(2):
                with pytest.raises(SourceAdapterError) as exc:
                    await source.fetch_page(CollectionRequest(organization="Wells Fargo"))
                errors.append(exc.value)
            return errors
        finally:
            await client.aclose()

    errors = run(scenario())
    assert [error.code for error in errors] == ["malformed_search_json", "unexpected_search_shape"]


def test_invalid_cursor_and_no_authentication_endpoints():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, json={"total": 0, "jobPostings": []})

    async def scenario():
        source, client = adapter(handler)
        try:
            with pytest.raises(SourceAdapterError, match="invalid collection cursor"):
                await source.fetch_page(CollectionRequest(organization="Wells Fargo"), "bad-cursor")
        finally:
            await client.aclose()

    run(scenario())
    assert seen == []
