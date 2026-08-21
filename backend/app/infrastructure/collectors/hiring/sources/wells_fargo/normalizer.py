from datetime import date, datetime
from html.parser import HTMLParser
import re
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from backend.app.domain.hiring.models import EmploymentType, JobPosting
from backend.app.domain.intelligence.evidence import Evidence, SourceType
from backend.app.domain.organization import OrganizationIdentity
from backend.app.infrastructure.collectors.hiring.contracts import RawJobRecord
from backend.app.infrastructure.collectors.hiring.protocols import RecordNormalizationError
from backend.app.application.hiring.collection import CollectedJob, CollectionRequest
from .contracts import WellsFargoRawPayload


class _HtmlTextParser(HTMLParser):
    _block_tags = {"br", "div", "li", "ol", "p", "ul", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._block_tags:
            self.parts.append("\n")


class WellsFargoJobNormalizer:
    collector_identity = "wells-fargo-workday-normalizer-v1"
    organization = OrganizationIdentity(key="wells_fargo", display_name="Wells Fargo")
    source_id = "wells-fargo-workday"
    _employment_types = {
        "full time": EmploymentType.FULL_TIME,
        "part time": EmploymentType.PART_TIME,
        "contract": EmploymentType.CONTRACT,
        "temporary": EmploymentType.TEMPORARY,
        "intern": EmploymentType.INTERNSHIP,
        "internship": EmploymentType.INTERNSHIP,
    }

    def normalize(self, record: RawJobRecord, request: CollectionRequest) -> CollectedJob:
        if request.organization != self.organization.display_name:
            raise RecordNormalizationError(
                "collection organization does not match the Wells Fargo source",
                code="organization_mismatch",
            )
        try:
            payload = WellsFargoRawPayload.model_validate(record.payload)
        except ValidationError as exc:
            raise RecordNormalizationError("invalid Wells Fargo Workday payload", metadata={"error": str(exc)}) from exc

        info = payload.job_detail.job_posting_info
        job_req_id = self._required(info.job_req_id, "missing_requisition_id")
        title = self._required(info.title or payload.search_summary.title, "missing_title")
        posted_date = self._parse_date(info.start_date, "invalid_posted_date")
        description = self._plain_text(info.job_description)
        if not description:
            raise RecordNormalizationError("missing_job_description", code="missing_description")
        location = self._location(info.location, info.additional_locations)
        country = self._country(info)
        source_url = info.external_url or str(record.source_url)
        closing_date = self._closing_date(payload.search_summary.bullet_fields)
        raw_reference = f"workday:wf:WellsFargoJobs:{job_req_id}"
        evidence_id = uuid5(NAMESPACE_URL, f"{self.collector_identity}:evidence:{raw_reference}")
        job_id = uuid5(NAMESPACE_URL, f"{self.collector_identity}:job:{raw_reference}")
        evidence = Evidence(
            evidence_id=evidence_id,
            source_url=source_url,
            source_type=SourceType.CAREER_SITE,
            source_title=title,
            retrieved_at=record.retrieved_at,
            source_excerpt=description[:497].rstrip() + "..." if len(description) > 500 else description,
            raw_reference=raw_reference,
            collector_identity=self.collector_identity,
            provenance_metadata={**record.provenance_metadata, "organization_key": self.organization.key, "source_id": self.source_id, "source_system": "Workday", "tenant": "wf", "site_id": "WellsFargoJobs", "source_record_id": record.source_record_id, "job_req_id": job_req_id, "run_id": str(request.run_id)},
        )
        try:
            job = JobPosting(
                job_id=job_id, organization=self.organization.display_name, source_job_id=job_req_id, title=title,
                description=description, location=location, country=country,
                posted_date=posted_date, closing_date=closing_date,
                employment_type=self._employment_type(info.time_type), source_url=source_url,
                evidence_id=evidence_id,
            )
        except ValidationError as exc:
            raise RecordNormalizationError("invalid normalized Wells Fargo job", metadata={"error": str(exc)}) from exc
        return CollectedJob(posting=job, evidence=evidence)

    @staticmethod
    def _required(value: str | None, code: str) -> str:
        if not value or not value.strip():
            raise RecordNormalizationError(code, code=code)
        return value.strip()

    @staticmethod
    def _parse_date(value: str | None, code: str) -> date:
        try:
            return date.fromisoformat(value or "")
        except ValueError as exc:
            raise RecordNormalizationError(code, code=code) from exc

    @staticmethod
    def _plain_text(value: str | None) -> str:
        if not value:
            return ""
        parser = _HtmlTextParser()
        parser.feed(value)
        text = re.sub(r"[ \t\f\v]+", " ", "".join(parser.parts))
        return re.sub(r"\n\s*\n+", "\n", text).strip()

    @staticmethod
    def _location(primary: str | None, additional: list[str]) -> str:
        values: list[str] = []
        for value in [primary, *additional]:
            if value and value.strip() and value.strip() not in values:
                values.append(value.strip())
        if not values:
            raise RecordNormalizationError("missing_location", code="missing_location")
        return " / ".join(values)

    @staticmethod
    def _country(info) -> str:
        nested = info.job_requisition_location.get("country", {})
        value = nested.get("alpha2Code") or info.country.get("alpha2Code")
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2}", value.strip()):
            raise RecordNormalizationError("missing_country_code", code="missing_country")
        return value.strip().upper()

    @classmethod
    def _employment_type(cls, value: str | None) -> EmploymentType | None:
        return cls._employment_types.get(value.strip().lower()) if value else None

    @staticmethod
    def _closing_date(fields: list[str]) -> date | None:
        for field in fields:
            match = re.match(r"\s*Posting End Date\s*:\s*(.+?)\s*$", field, re.IGNORECASE)
            if match:
                value = match.group(1)
                for fmt in (None, "%m/%d/%Y", "%m/%d/%y"):
                    try:
                        return date.fromisoformat(value) if fmt is None else datetime.strptime(value, fmt).date()
                    except ValueError:
                        continue
                raise RecordNormalizationError("invalid_closing_date", code="invalid_closing_date")
        return None
