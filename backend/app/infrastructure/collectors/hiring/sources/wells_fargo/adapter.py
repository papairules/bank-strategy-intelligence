from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.app.application.hiring import CollectionIssueStage, CollectionRequest
from backend.app.infrastructure.collectors.hiring.contracts import (
    RawJobPage,
    RawJobRecord,
    SourceIssueStage,
    SourceRecordIssue,
)
from backend.app.infrastructure.collectors.hiring.protocols import (
    SourceAdapter,
    SourceAdapterError,
)


class WellsFargoSourceAdapter(SourceAdapter):
    collector_id = "wells-fargo-workday-adapter-v1"
    source_id = "wells-fargo-workday"
    search_url = "https://wf.wd1.myworkdayjobs.com/wday/cxs/wf/WellsFargoJobs/jobs"
    public_job_base_url = "https://wf.wd1.myworkdayjobs.com/WellsFargoJobs"
    detail_base_url = "https://wf.wd1.myworkdayjobs.com/wday/cxs/wf/WellsFargoJobs"
    user_agent = "BankStrategyIntelligence/0.1 internal POC hiring collector"
    page_size = 20

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_retries: int = 2,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self._client = client
        self._max_retries = max_retries
        self._sleeper = sleeper
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build_search_request(self, offset: int) -> dict[str, Any]:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        return {"appliedFacets": {}, "limit": self.page_size, "offset": offset, "searchText": ""}

    async def fetch_page(self, request: CollectionRequest, cursor: str | None = None) -> RawJobPage:
        offset = self._parse_cursor(cursor)
        search_retrieved_at = self._clock()
        response = await self._request("POST", self.search_url, json=self.build_search_request(offset))
        search_payload = self._json_object(response, "search", response.status_code)
        postings = search_payload.get("jobPostings")
        total = search_payload.get("total")
        if not isinstance(postings, list) or not isinstance(total, int) or total < 0:
            raise SourceAdapterError("unexpected Workday search response shape", code="unexpected_search_shape", stage=CollectionIssueStage.PARSE, metadata={"http_status": response.status_code})

        records: list[RawJobRecord] = []
        issues: list[SourceRecordIssue] = []
        for position, summary in enumerate(postings):
            if not isinstance(summary, dict):
                issues.append(SourceRecordIssue(stage=SourceIssueStage.PARSE, code="invalid_search_record", message="Workday search record is not an object", record_position=position, metadata={"search_offset": offset}))
                continue
            external_path = summary.get("externalPath")
            source_record_id = self._summary_id(summary)
            if not isinstance(external_path, str) or not external_path.strip():
                issues.append(SourceRecordIssue(stage=SourceIssueStage.PARSE, code="missing_external_path", message="Workday search record has no externalPath", source_record_id=source_record_id, record_position=position, metadata={"search_offset": offset}))
                continue
            detail_url = f"{self.detail_base_url}{external_path if external_path.startswith('/') else '/' + external_path}"
            try:
                detail_retrieved_at = self._clock()
                detail_response = await self._request("GET", detail_url)
                detail_payload = self._json_object(detail_response, "detail", detail_response.status_code)
                self._validate_detail(detail_payload)
                raw_id = source_record_id or self._detail_id(detail_payload) or external_path
                records.append(RawJobRecord(
                    source_record_id=raw_id,
                    source_url=f"{self.public_job_base_url}{external_path if external_path.startswith('/') else '/' + external_path}",
                    retrieved_at=detail_retrieved_at,
                    payload={"search_summary": summary, "job_detail": detail_payload},
                    source_title=summary.get("title") if isinstance(summary.get("title"), str) else None,
                    provenance_metadata={"tenant": "wf", "site": "WellsFargoJobs", "collector": self.collector_id, "search_endpoint": self.search_url, "detail_endpoint": detail_url, "search_offset": offset, "search_limit": self.page_size, "search_result_position": position, "external_path": external_path, "search_retrieved_at": search_retrieved_at.isoformat(), "detail_retrieved_at": detail_retrieved_at.isoformat(), "search_http_status": response.status_code, "detail_http_status": detail_response.status_code, "search_content_type": response.headers.get("content-type", ""), "detail_content_type": detail_response.headers.get("content-type", ""), **({"requisition_id": source_record_id} if source_record_id else {})},
                ))
            except SourceAdapterError as error:
                issues.append(SourceRecordIssue(stage=SourceIssueStage.FETCH if error.stage.value == "fetch" else SourceIssueStage.PARSE, code=error.code, message=str(error), recoverable=error.recoverable, source_record_id=source_record_id, record_position=position, metadata={"external_path": external_path, "search_offset": offset, **error.metadata}))

        next_cursor = str(offset + len(postings)) if offset + len(postings) < total and postings else None
        return RawJobPage(records=records, source_issues=issues, next_cursor=next_cursor, page_metadata={"total": total, "offset": offset, "limit": self.page_size, "search_http_status": response.status_code, "retrieved_at": search_retrieved_at.isoformat()})

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(method, url, headers=headers, **kwargs)
            except httpx.HTTPError as exc:
                raise SourceAdapterError("Workday request failed", code="http_request_error", recoverable=False, metadata={"exception_type": type(exc).__name__}) from exc
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt < self._max_retries:
                    await self._sleeper(self._retry_delay(response, attempt))
                    continue
                raise SourceAdapterError("Workday request retry limit exhausted", code="rate_limited" if response.status_code == 429 else "transient_http_error", recoverable=True, metadata={"http_status": response.status_code})
            if response.status_code >= 400:
                raise SourceAdapterError(f"Workday request returned HTTP {response.status_code}", code="forbidden" if response.status_code == 403 else "http_error", recoverable=response.status_code in {408, 409}, metadata={"http_status": response.status_code})
            return response
        raise AssertionError("unreachable retry state")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        try:
            return max(0.0, float(value)) if value is not None else float(2**attempt)
        except ValueError:
            return float(2**attempt)

    @staticmethod
    def _json_object(response: httpx.Response, kind: str, status: int) -> dict[str, Any]:
        try:
            value = response.json()
        except (ValueError, TypeError) as exc:
            raise SourceAdapterError(f"malformed Workday {kind} JSON", code=f"malformed_{kind}_json", stage=CollectionIssueStage.PARSE, metadata={"http_status": status}) from exc
        if not isinstance(value, dict):
            raise SourceAdapterError(f"Workday {kind} response is not an object", code=f"unexpected_{kind}_shape", stage=CollectionIssueStage.PARSE, metadata={"http_status": status})
        return value

    @staticmethod
    def _validate_detail(payload: dict[str, Any]) -> None:
        if not isinstance(payload.get("jobPostingInfo"), dict):
            raise SourceAdapterError("unexpected Workday detail response shape", code="unexpected_detail_shape", stage=CollectionIssueStage.PARSE)

    @staticmethod
    def _summary_id(summary: dict[str, Any]) -> str | None:
        for value in summary.get("bulletFields", []):
            if isinstance(value, str) and value.startswith("R-"):
                return value
        return None

    @staticmethod
    def _detail_id(payload: dict[str, Any]) -> str | None:
        value = payload.get("jobPostingInfo", {}).get("jobReqId")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            offset = int(cursor)
        except (TypeError, ValueError) as exc:
            raise SourceAdapterError("invalid collection cursor", code="invalid_cursor", recoverable=False) from exc
        if offset < 0:
            raise SourceAdapterError("invalid collection cursor", code="invalid_cursor", recoverable=False)
        return offset
