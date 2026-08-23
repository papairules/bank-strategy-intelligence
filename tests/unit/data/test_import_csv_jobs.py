from pathlib import Path

import pytest

from backend.app.application.hiring import HiringPersistenceService
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase
from data.import_csv_jobs import (
    CSVRowValidationError,
    _persisted_projection,
    build_canonical_import,
    validate_csv,
)


CSV_ROOT = Path("data/csv")
CSV_EXPECTATIONS = {
    "active_jobs_barclays_20260821T210311.csv": ("Barclays", 113, 112),
    "active_jobs_bny_20260821T204510.csv": ("BNY", 1120, 1120),
    "active_jobs_citibank_20260821T204521.csv": ("Citibank", 1169, 1169),
    "active_jobs_goldman_sachs_20260821T204513.csv": ("Goldman Sachs", 755, 755),
    "active_jobs_morgan_stanley_20260821T204518.csv": ("Morgan Stanley", 933, 933),
    "active_jobs_wells_fargo_20260821T204507.csv": ("Wells Fargo", 1610, 1610),
}


def test_all_finalized_csvs_validate_through_canonical_import(tmp_path):
    database = SQLiteDatabase(tmp_path / "csv-validation.sqlite3")
    database.initialize()

    for filename, (organization, source_rows, accepted_rows) in CSV_EXPECTATIONS.items():
        diagnostics, imports = validate_csv(CSV_ROOT / filename, database)
        assert diagnostics.source_rows == source_rows
        assert diagnostics.valid_rows == accepted_rows
        assert diagnostics.rejected_rows == source_rows - accepted_rows
        assert {item.identity.organization.display_name for item in imports} == {organization}
        assert all(item.posting.source_job_id.startswith("csv_import:") for item in imports)


def test_barclays_incomplete_row_is_rejected_with_explicit_reasons(tmp_path):
    database = SQLiteDatabase(tmp_path / "csv-validation.sqlite3")
    database.initialize()
    diagnostics, _ = validate_csv(
        CSV_ROOT / "active_jobs_barclays_20260821T210311.csv", database
    )

    rejection = next(
        item for item in diagnostics.rejections if item.external_job_id == "98184709568"
    )
    assert rejection.organization == "BARCLAYS"
    assert rejection.reasons == ("missing_country",)


def test_missing_and_invalid_posting_dates_are_rejected_without_fallback():
    row = {
        "company": "BNY",
        "source_job_id": "1",
        "title": "Analyst",
        "description_text": "Authoritative description",
        "country": "US",
        "posting_url": "https://example.test/1",
        "source_posted_at": "",
        "first_seen_at": "",
    }
    with pytest.raises(CSVRowValidationError, match="missing_posting_date"):
        build_canonical_import(row)

    row["source_posted_at"] = "not-a-date"
    row["first_seen_at"] = "2026-08-20"
    with pytest.raises(CSVRowValidationError, match="invalid_source_posted_at"):
        build_canonical_import(row)


def test_first_seen_date_is_explicit_fallback_and_is_provenanced():
    row = {
        "company": "Goldman Sachs",
        "source_job_id": "12345",
        "title": "Engineer",
        "description_text": "Authoritative description",
        "country": "US",
        "first_seen_at": "2026-08-20 12:00:00",
        "posting_url": "https://example.test/12345",
    }
    item = build_canonical_import(row)
    assert item.posting.posted_date.isoformat() == "2026-08-20"
    assert item.evidence.provenance_metadata["posting_date_source"] == "first_seen_at"


def test_canonical_identity_is_deterministic_and_evidence_is_linked():
    row = {
        "company": "Goldman Sachs",
        "source_job_id": "12345",
        "title": "Engineer",
        "description_text": "Authoritative description",
        "country": "US",
        "source_posted_at": "2026-08-20",
        "posting_url": "https://example.test/12345",
    }
    first = build_canonical_import(row)
    second = build_canonical_import(row)

    assert first.identity == second.identity
    assert first.posting.job_id == second.posting.job_id
    assert first.evidence.evidence_id == second.evidence.evidence_id
    assert first.posting.evidence_id == first.evidence.evidence_id
    assert first.evidence.provenance_metadata["organization_key"] == "goldman_sachs"


def test_persistence_projection_preserves_legacy_source_key_and_is_idempotent(tmp_path):
    database = SQLiteDatabase(tmp_path / "csv-persistence.sqlite3")
    database.initialize()
    rows = [
        {
            "company": organization,
            "source_job_id": "same-id",
            "title": "Engineer",
            "description_text": "Authoritative description",
            "country": "US",
            "source_posted_at": "2026-08-20",
            "posting_url": f"https://example.test/{organization}",
        }
        for organization in ("Wells Fargo", "BNY")
    ]
    imports = [build_canonical_import(row) for row in rows]
    persisted = [_persisted_projection(item) for item in imports]
    service = HiringPersistenceService(database.unit_of_work)
    service.save_collected_jobs(persisted)
    service.save_collected_jobs(persisted)

    with database.unit_of_work() as unit_of_work:
        jobs = unit_of_work.job_postings.list_all()
        evidence = unit_of_work.evidence.list_all()
    assert len(jobs) == 2
    assert len(evidence) == 2
    assert {item.source_job_id for item in jobs} == {"same-id"}
    assert len({item.job_id for item in jobs}) == 2
