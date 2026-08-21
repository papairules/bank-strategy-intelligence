from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.app.application.hiring import CollectionRequest
from backend.app.domain.hiring import EmploymentType
from backend.app.domain.intelligence import SourceType
from backend.app.infrastructure.collectors.hiring.contracts import RawJobRecord
from backend.app.infrastructure.collectors.hiring.protocols import RecordNormalizationError
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.fixtures import (
    copy_payload,
    international,
    missing_optional,
    multiple_locations,
    part_time,
    standard_us_full_time,
)
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.normalizer import WellsFargoJobNormalizer


RUN_ID = UUID("00000000-0000-0000-0000-000000000001")


def raw_record(payload: dict, source_id: str = "R-100001") -> RawJobRecord:
    return RawJobRecord(
        source_record_id=source_id,
        source_url="https://wd1.myworkdaysite.com/recruiting/wf/WellsFargoJobs/job/Synthetic",
        retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        payload=payload,
        provenance_metadata={"fixture": "synthetic"},
    )


def normalize(payload: dict, source_id: str = "R-100001"):
    return WellsFargoJobNormalizer().normalize(raw_record(payload, source_id), CollectionRequest(organization="Wells Fargo", run_id=RUN_ID))


def test_maps_core_fields_and_evidence():
    result = normalize(standard_us_full_time())
    posting = result.posting
    assert posting.source_job_id == "R-100001"
    assert posting.title == "Senior Platform Engineer"
    assert posting.location == "Charlotte, NC"
    assert posting.country == "US"
    assert posting.posted_date.isoformat() == "2026-08-01"
    assert posting.closing_date.isoformat() == "2026-08-31"
    assert posting.employment_type is EmploymentType.FULL_TIME
    assert str(posting.source_url) == "https://wd1.myworkdaysite.com/recruiting/wf/WellsFargoJobs/job/Senior-Platform-Engineer_R-100001"
    assert result.evidence.source_type is SourceType.CAREER_SITE
    assert result.evidence.source_title == posting.title
    assert result.evidence.raw_reference == "workday:wf:WellsFargoJobs:R-100001"
    assert result.evidence.evidence_id == posting.evidence_id
    assert "Build safely" in posting.description
    assert "<h2>" not in posting.description
    assert len(result.evidence.source_excerpt) <= 500


def test_maps_multiple_locations_and_country():
    result = normalize(multiple_locations(), "R-100003")
    assert result.posting.location == "Charlotte, NC / Minneapolis, MN / New York, NY"
    international_result = normalize(international(), "R-100004")
    assert international_result.posting.country == "IN"


def test_maps_part_time_and_missing_optional_closing_date():
    assert normalize(part_time(), "R-100002").posting.employment_type is EmploymentType.PART_TIME
    assert normalize(missing_optional(), "R-100001").posting.closing_date is None


@pytest.mark.parametrize(("field", "code"), [("jobReqId", "missing_requisition_id"), ("startDate", "invalid_posted_date")])
def test_rejects_malformed_required_fields(field: str, code: str):
    payload = standard_us_full_time()
    payload["job_detail"]["jobPostingInfo"][field] = "" if field == "jobReqId" else "not-a-date"
    with pytest.raises(RecordNormalizationError, match=code):
        normalize(payload)


def test_payload_is_unchanged_and_output_is_deterministic():
    payload = standard_us_full_time()
    original = deepcopy(payload)
    first = normalize(payload)
    second = normalize(payload)
    assert payload == original
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_intelligence_fields_remain_unpopulated():
    posting = normalize(standard_us_full_time()).posting
    assert posting.business_unit is None
    assert posting.capability_classifications == []
    assert posting.skills == []
    assert posting.technologies == []
    assert posting.seniority_level is None
    assert posting.is_leadership is False
