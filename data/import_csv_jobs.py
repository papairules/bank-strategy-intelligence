"""Validate and import finalized hiring CSV snapshots.

The CSV is an authoritative source snapshot, while SQLite remains the
application system of record. Validation is performed through
``CanonicalJobImport`` before the existing persistence service is called.
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.application.hiring import CollectedJob, HiringPersistenceService  # noqa: E402
from backend.app.application.hiring.imports import CanonicalJobIdentity, CanonicalJobImport  # noqa: E402
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


class CSVRowValidationError(ValueError):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = tuple(dict.fromkeys(reasons))
        super().__init__(", ".join(self.reasons))


@dataclass(frozen=True)
class ImportRejection:
    row_number: int
    organization: str | None
    external_job_id: str | None
    reasons: tuple[str, ...]


@dataclass
class ImportDiagnostics:
    csv_path: str
    source: str = SOURCE_ID
    source_rows: int = 0
    valid_rows: int = 0
    imported_rows: int = 0
    idempotent_rows: int = 0
    rejected_rows: int = 0
    rejections: list[ImportRejection] = field(default_factory=list)
    organization_counts: dict[str, int] = field(default_factory=dict)
    evidence_counts: dict[str, int] = field(default_factory=dict)


def resolve_organization(company_value: str) -> OrganizationIdentity:
    token = company_value.strip().upper()
    if token not in _organization_cache:
        display_name = DISPLAY_NAME_OVERRIDES.get(token) or token.replace("_", " ").title()
        _organization_cache[token] = OrganizationIdentity(
            key=organization_key(display_name),
            display_name=display_name,
        )
    return _organization_cache[token]


def _required_value(row: dict[str, str], field_name: str, reasons: list[str]) -> str:
    value = (row.get(field_name) or "").strip()
    if not value:
        reasons.append(f"missing_{field_name}")
    return value


def _posted_date(row: dict[str, str], reasons: list[str]) -> tuple[date | None, str | None]:
    source_posted_at = (row.get("source_posted_at") or "").strip()
    if source_posted_at:
        try:
            return date.fromisoformat(source_posted_at[:10]), "source_posted_at"
        except ValueError:
            reasons.append("invalid_source_posted_at")
            return None, None
    first_seen_at = (row.get("first_seen_at") or "").strip()
    if first_seen_at:
        try:
            return date.fromisoformat(first_seen_at[:10]), "first_seen_at"
        except ValueError:
            reasons.append("invalid_first_seen_at")
            return None, None
    reasons.append("missing_posting_date")
    return None, None


def build_canonical_import(row: dict[str, str]) -> CanonicalJobImport:
    reasons: list[str] = []
    company_value = _required_value(row, "company", reasons)
    external_job_id = _required_value(row, "source_job_id", reasons)
    title = _required_value(row, "title", reasons)
    description = _required_value(row, "description_text", reasons)
    posting_url = _required_value(row, "posting_url", reasons)
    country = _required_value(row, "country", reasons)
    posted_date, posted_date_source = _posted_date(row, reasons)
    if reasons:
        raise CSVRowValidationError(reasons)

    organization = resolve_organization(company_value)
    identity = CanonicalJobIdentity(
        organization=organization,
        source_id=SOURCE_ID,
        external_job_id=external_job_id,
    )
    location = ", ".join(
        filter(None, [(row.get("city") or "").strip(), (row.get("state") or "").strip()])
    ) or "Unknown"
    employment_type = EMPLOYMENT_TYPE_MAP.get(
        (row.get("employment_type") or "").strip().casefold()
    )
    posting = JobPosting(
        job_id=identity.job_id,
        organization=organization.display_name,
        source_job_id=identity.source_scoped_job_id,
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
        raw_reference=f"csv_import:{organization.key}:{external_job_id}",
        collector_identity="csv-import-script",
        provenance_metadata={
            "organization_key": organization.key,
            "source_id": SOURCE_ID,
            "external_job_id": external_job_id,
            "posting_date_source": posted_date_source,
        },
    )
    return CanonicalJobImport(identity=identity, posting=posting, evidence=evidence)


def build_collected_job(row: dict[str, str]) -> CanonicalJobImport:
    """Backward-compatible name for callers that build one CSV record."""
    return build_canonical_import(row)


def _persisted_projection(item: CanonicalJobImport) -> CollectedJob:
    """Preserve the legacy persisted source_job_id without changing UUIDs."""
    posting = item.posting.model_copy(
        update={"source_job_id": item.identity.external_job_id}
    )
    return CollectedJob(posting=posting, evidence=item.evidence)


def _existing_source_ids(database: SQLiteDatabase) -> set[tuple[str, str]]:
    with database.unit_of_work() as unit_of_work:
        return {
            (posting.organization, posting.source_job_id)
            for posting in unit_of_work.job_postings.list_all()
        }


def _counts(database: SQLiteDatabase) -> tuple[dict[str, int], dict[str, int]]:
    with database.unit_of_work() as unit_of_work:
        jobs = unit_of_work.job_postings.list_all()
        evidence = unit_of_work.evidence.list_all()
    job_counts: dict[str, int] = {}
    evidence_counts: dict[str, int] = {}
    for posting in jobs:
        job_counts[posting.organization] = job_counts.get(posting.organization, 0) + 1
    for item in evidence:
        organization = item.provenance_metadata.get("organization_key", "unknown")
        evidence_counts[str(organization)] = evidence_counts.get(str(organization), 0) + 1
    return job_counts, evidence_counts


def validate_csv(csv_path: Path, database: SQLiteDatabase) -> tuple[ImportDiagnostics, list[CanonicalJobImport]]:
    diagnostics = ImportDiagnostics(csv_path=str(csv_path))
    existing = _existing_source_ids(database)
    valid: list[CanonicalJobImport] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for row_number, row in enumerate(reader, start=2):
            diagnostics.source_rows += 1
            try:
                item = build_canonical_import(row)
            except (CSVRowValidationError, ValueError) as error:
                reasons = error.reasons if isinstance(error, CSVRowValidationError) else ("canonical_validation_failed",)
                diagnostics.rejections.append(
                    ImportRejection(
                        row_number=row_number,
                        organization=(row.get("company") or "").strip() or None,
                        external_job_id=(row.get("source_job_id") or "").strip() or None,
                        reasons=tuple(reasons),
                    )
                )
                continue
            diagnostics.valid_rows += 1
            valid.append(item)
            key = (item.identity.organization.display_name, item.identity.external_job_id)
            if key in existing:
                diagnostics.idempotent_rows += 1
            else:
                diagnostics.imported_rows += 1
    diagnostics.rejected_rows = len(diagnostics.rejections)
    return diagnostics, valid


def import_csv(csv_path: Path, *, dry_run: bool = False) -> ImportDiagnostics:
    settings = HiringSettings()
    database = SQLiteDatabase(settings.sqlite_database_path)
    database.initialize()
    diagnostics, canonical_items = validate_csv(csv_path, database)
    if not dry_run and canonical_items:
        persistence = HiringPersistenceService(database.unit_of_work)
        persistence.save_collected_jobs([_persisted_projection(item) for item in canonical_items])
    diagnostics.organization_counts, diagnostics.evidence_counts = _counts(database)
    return diagnostics


def _print_diagnostics(diagnostics: ImportDiagnostics, *, dry_run: bool) -> None:
    mode = "dry-run" if dry_run else "import"
    print(f"{mode}: {diagnostics.csv_path}")
    print(
        "source_rows={source_rows} valid_rows={valid_rows} imported_rows={imported_rows} "
        "idempotent_rows={idempotent_rows} rejected_rows={rejected_rows}".format(
            **diagnostics.__dict__
        )
    )
    if diagnostics.organization_counts:
        print(f"job_counts={diagnostics.organization_counts}")
    if diagnostics.evidence_counts:
        print(f"evidence_counts_by_organization_key={diagnostics.evidence_counts}")
    for rejection in diagnostics.rejections:
        print(
            f"rejected row={rejection.row_number} organization={rejection.organization!r} "
            f"external_job_id={rejection.external_job_id!r} reasons={','.join(rejection.reasons)}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_paths", type=Path, nargs="+", help="CSV snapshot paths.")
    parser.add_argument("--dry-run", action="store_true", help="Validate without persistence writes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for csv_path in args.csv_paths:
        if not csv_path.is_file():
            print(f"error: {csv_path} is not a file", file=sys.stderr)
            return 1
    for csv_path in args.csv_paths:
        _print_diagnostics(import_csv(csv_path, dry_run=args.dry_run), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
