"""Import an active-jobs CSV snapshot into the app's SQLite database.

Usage (from anywhere; the script resolves the repo root itself):

    python data/import_csv_jobs.py data/csv/active_jobs_wells_fargo_20260821T204507.csv

The CSV is expected to use the same columns as the Hiring Agent's sample
snapshots: company, source_job_id, title, role_family, city, state, country,
workplace_type, employment_type, description_text, qualifications_text,
responsibilities_text, first_seen_at, source_posted_at, posting_url.

Records are upserted using the app's normal (organization, source_job_id) key,
so re-running this script against the same file is safe and idempotent. The
organization is read from each row's `company` column, so a single run can
cover a file that mixes multiple companies.

This writes real JobPosting/Evidence records into the configured database
(BSI_SQLITE_DATABASE_PATH, default data/hiring-intelligence.sqlite3) using
the same persistence layer the live Wells Fargo collector uses. It does not
run classification or enrichment; that happens later via the Hiring Agent or
the app's enrichment pipeline.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.application.hiring import CollectedJob, HiringPersistenceService  # noqa: E402
from backend.app.application.hiring.imports import CanonicalJobIdentity  # noqa: E402
from backend.app.config import HiringSettings  # noqa: E402
from backend.app.domain.hiring import EmploymentType, JobPosting  # noqa: E402
from backend.app.domain.intelligence import Evidence  # noqa: E402
from backend.app.domain.organization import OrganizationIdentity, organization_key  # noqa: E402
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase  # noqa: E402

SOURCE_ID = "csv_import"

DISPLAY_NAME_OVERRIDES = {
    "WELLS_FARGO": "Wells Fargo",
    "BARCLAYS": "Barclays",
    "BNY": "BNY",
    "CITIBANK": "Citibank",
    "GOLDMAN_SACHS": "Goldman Sachs",
    "MORGAN_STANLEY": "Morgan Stanley",
}

EMPLOYMENT_TYPE_MAP = {
    "full time": EmploymentType.FULL_TIME,
    "part time": EmploymentType.PART_TIME,
    "permanent": EmploymentType.FULL_TIME,
    "contract": EmploymentType.CONTRACT,
    "contractor": EmploymentType.CONTRACT,
    "temporary": EmploymentType.TEMPORARY,
    "intern": EmploymentType.INTERNSHIP,
    "internship": EmploymentType.INTERNSHIP,
}

_organization_cache: dict[str, OrganizationIdentity] = {}


def resolve_organization(company_value: str) -> OrganizationIdentity:
    token = company_value.strip().upper()
    if token not in _organization_cache:
        display_name = DISPLAY_NAME_OVERRIDES.get(token) or token.replace("_", " ").title()
        _organization_cache[token] = OrganizationIdentity(
            key=organization_key(display_name),
            display_name=display_name,
        )
    return _organization_cache[token]


def build_collected_job(row: dict[str, str]) -> CollectedJob | None:
    company_value = (row.get("company") or "").strip()
    source_job_id = (row.get("source_job_id") or "").strip()
    title = (row.get("title") or "").strip()
    description = (row.get("description_text") or "").strip()
    posting_url = (row.get("posting_url") or "").strip()
    country = (row.get("country") or "").strip()
    if not company_value or not source_job_id or not title or not description or not posting_url or not country:
        return None

    organization = resolve_organization(company_value)
    identity = CanonicalJobIdentity(organization=organization, source_id=SOURCE_ID, external_job_id=source_job_id)

    posted_raw = (row.get("source_posted_at") or row.get("first_seen_at") or "").strip()
    try:
        posted_date = date.fromisoformat(posted_raw[:10]) if posted_raw else date.today()
    except ValueError:
        posted_date = date.today()

    location = ", ".join(filter(None, [(row.get("city") or "").strip(), (row.get("state") or "").strip()])) or "Unknown"
    employment_type = EMPLOYMENT_TYPE_MAP.get((row.get("employment_type") or "").strip().casefold())

    posting = JobPosting(
        job_id=identity.job_id,
        organization=organization.display_name,
        source_job_id=source_job_id,
        title=title,
        description=description,
        location=location,
        country=country,
        posted_date=posted_date,
        employment_type=employment_type,
        source_url=posting_url,
        evidence_id=identity.evidence_id,
    )
    evidence = Evidence(
        evidence_id=identity.evidence_id,
        source_url=posting_url,
        source_type="career_site",
        source_title=title,
        retrieved_at=datetime.now(timezone.utc),
        source_excerpt=description[:500],
        raw_reference=f"csv_import:{organization.key}:{source_job_id}",
        collector_identity="csv-import-script",
        provenance_metadata={
            "organization_key": organization.key,
            "source_id": SOURCE_ID,
            "external_job_id": source_job_id,
        },
    )
    return CollectedJob(posting=posting, evidence=evidence)


def import_csv(csv_path: Path) -> None:
    settings = HiringSettings()
    database = SQLiteDatabase(settings.sqlite_database_path)
    database.initialize()
    persistence = HiringPersistenceService(database.unit_of_work)

    jobs: list[CollectedJob] = []
    skipped = 0
    with csv_path.open(encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            job = build_collected_job(row)
            if job is None:
                skipped += 1
                continue
            jobs.append(job)

    saved = persistence.save_collected_jobs(jobs)
    organizations = sorted({job.posting.organization for job in jobs})
    print(f"imported {saved} jobs into {settings.sqlite_database_path}")
    print(f"organizations touched: {', '.join(organizations) if organizations else 'none'}")
    print(f"skipped {skipped} incomplete rows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Path to an active-jobs CSV snapshot.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.csv_path.is_file():
        print(f"error: {args.csv_path} is not a file", file=sys.stderr)
        return 1
    import_csv(args.csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
