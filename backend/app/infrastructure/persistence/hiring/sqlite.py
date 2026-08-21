from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import TracebackType
from uuid import UUID

from backend.app.application.hiring.observability import CollectionRun
from backend.app.application.hiring.persistence import PersistenceError
from backend.app.domain.hiring import EmploymentType, JobPosting
from backend.app.domain.intelligence import Evidence


SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_title TEXT,
    retrieved_at TEXT NOT NULL,
    source_excerpt TEXT,
    raw_reference TEXT,
    collector_identity TEXT NOT NULL,
    provenance_metadata TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_postings (
    job_id TEXT PRIMARY KEY,
    organization TEXT NOT NULL,
    source_job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    location TEXT NOT NULL,
    country TEXT NOT NULL,
    business_unit TEXT,
    capability_classifications TEXT NOT NULL,
    skills TEXT NOT NULL,
    technologies TEXT NOT NULL,
    seniority_level TEXT,
    is_leadership INTEGER NOT NULL CHECK (is_leadership IN (0, 1)),
    posted_date TEXT NOT NULL,
    closing_date TEXT,
    employment_type TEXT,
    source_url TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    UNIQUE (organization, source_job_id)
);

CREATE INDEX IF NOT EXISTS idx_job_postings_evidence_id
    ON job_postings(evidence_id);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    collector_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    organization TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'partial', 'failed')),
    pages_attempted INTEGER NOT NULL CHECK (pages_attempted >= 0),
    records_encountered INTEGER NOT NULL CHECK (records_encountered >= 0),
    records_collected INTEGER NOT NULL CHECK (records_collected >= 0),
    records_skipped INTEGER NOT NULL CHECK (records_skipped >= 0),
    issue_count INTEGER NOT NULL CHECK (issue_count >= 0),
    resume_cursor TEXT,
    source_metadata TEXT NOT NULL,
    CHECK (records_encountered = records_collected + records_skipped)
);

CREATE INDEX IF NOT EXISTS idx_collection_runs_completed_at
    ON collection_runs(completed_at DESC);

CREATE INDEX IF NOT EXISTS idx_collection_runs_organization_completed_at
    ON collection_runs(organization, completed_at DESC);
"""


class SQLiteDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def unit_of_work(self) -> SQLiteHiringUnitOfWork:
        return SQLiteHiringUnitOfWork(self)


class SQLiteEvidenceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, evidence: Evidence) -> None:
        values = evidence.model_dump(mode="json")
        self._connection.execute(
            """
            INSERT INTO evidence (
                evidence_id, source_url, source_type, source_title, retrieved_at,
                source_excerpt, raw_reference, collector_identity,
                provenance_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(evidence_id) DO UPDATE SET
                source_url = excluded.source_url,
                source_type = excluded.source_type,
                source_title = excluded.source_title,
                retrieved_at = excluded.retrieved_at,
                source_excerpt = excluded.source_excerpt,
                raw_reference = excluded.raw_reference,
                collector_identity = excluded.collector_identity,
                provenance_metadata = excluded.provenance_metadata
            """,
            (
                values["evidence_id"],
                values["source_url"],
                values["source_type"],
                values["source_title"],
                values["retrieved_at"],
                values["source_excerpt"],
                values["raw_reference"],
                values["collector_identity"],
                _dump_json(values["provenance_metadata"]),
            ),
        )

    def get(self, evidence_id: UUID) -> Evidence | None:
        row = self._connection.execute(
            "SELECT * FROM evidence WHERE evidence_id = ?",
            (str(evidence_id),),
        ).fetchone()
        return _evidence_from_row(row) if row is not None else None

    def list_all(self) -> list[Evidence]:
        rows = self._connection.execute(
            "SELECT * FROM evidence ORDER BY evidence_id"
        ).fetchall()
        return [_evidence_from_row(row) for row in rows]


class SQLiteJobPostingRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, posting: JobPosting) -> None:
        values = posting.model_dump(mode="json")
        self._connection.execute(
            """
            INSERT INTO job_postings (
                job_id, organization, source_job_id, title, description,
                location, country, business_unit, capability_classifications,
                skills, technologies, seniority_level, is_leadership,
                posted_date, closing_date, employment_type, source_url,
                evidence_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(organization, source_job_id) DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                location = excluded.location,
                country = excluded.country,
                business_unit = excluded.business_unit,
                capability_classifications = excluded.capability_classifications,
                skills = excluded.skills,
                technologies = excluded.technologies,
                seniority_level = excluded.seniority_level,
                is_leadership = excluded.is_leadership,
                posted_date = excluded.posted_date,
                closing_date = excluded.closing_date,
                employment_type = excluded.employment_type,
                source_url = excluded.source_url,
                evidence_id = excluded.evidence_id
            """,
            (
                values["job_id"],
                values["organization"],
                values["source_job_id"],
                values["title"],
                values["description"],
                values["location"],
                values["country"],
                values["business_unit"],
                _dump_json(values["capability_classifications"]),
                _dump_json(values["skills"]),
                _dump_json(values["technologies"]),
                values["seniority_level"],
                int(values["is_leadership"]),
                values["posted_date"],
                values["closing_date"],
                values["employment_type"],
                values["source_url"],
                values["evidence_id"],
            ),
        )

    def get(self, job_id: UUID) -> JobPosting | None:
        row = self._connection.execute(
            "SELECT * FROM job_postings WHERE job_id = ?",
            (str(job_id),),
        ).fetchone()
        return _job_posting_from_row(row) if row is not None else None

    def get_by_source_identity(
        self,
        organization: str,
        source_job_id: str,
    ) -> JobPosting | None:
        row = self._connection.execute(
            """
            SELECT * FROM job_postings
            WHERE organization = ? AND source_job_id = ?
            """,
            (organization, source_job_id),
        ).fetchone()
        return _job_posting_from_row(row) if row is not None else None

    def list_all(self) -> list[JobPosting]:
        rows = self._connection.execute(
            "SELECT * FROM job_postings ORDER BY organization, source_job_id"
        ).fetchall()
        return [_job_posting_from_row(row) for row in rows]

    def list_by_organization(self, organization: str) -> list[JobPosting]:
        rows = self._connection.execute(
            """
            SELECT * FROM job_postings
            WHERE organization = ?
            ORDER BY posted_date, job_id
            """,
            (organization,),
        ).fetchall()
        return [_job_posting_from_row(row) for row in rows]

    def search(
        self,
        *,
        organization: str | None,
        country: str | None,
        employment_type: EmploymentType | None,
        limit: int,
        offset: int,
    ) -> list[JobPosting]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        clauses: list[str] = []
        parameters: list[str | int] = []
        if organization is not None:
            clauses.append("organization = ?")
            parameters.append(organization)
        if country is not None:
            clauses.append("country = ?")
            parameters.append(country)
        if employment_type is not None:
            clauses.append("employment_type = ?")
            parameters.append(employment_type.value)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.extend([limit, offset])
        rows = self._connection.execute(
            f"""
            SELECT * FROM job_postings
            {where_clause}
            ORDER BY posted_date DESC, organization, source_job_id
            LIMIT ? OFFSET ?
            """,
            parameters,
        ).fetchall()
        return [_job_posting_from_row(row) for row in rows]


class SQLiteCollectionRunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, run: CollectionRun) -> None:
        values = run.model_dump(mode="json")
        self._connection.execute(
            """
            INSERT INTO collection_runs (
                run_id, collector_id, source_id, organization, started_at,
                completed_at, status, pages_attempted, records_encountered,
                records_collected, records_skipped, issue_count, resume_cursor,
                source_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                collector_id = excluded.collector_id,
                source_id = excluded.source_id,
                organization = excluded.organization,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at,
                status = excluded.status,
                pages_attempted = excluded.pages_attempted,
                records_encountered = excluded.records_encountered,
                records_collected = excluded.records_collected,
                records_skipped = excluded.records_skipped,
                issue_count = excluded.issue_count,
                resume_cursor = excluded.resume_cursor,
                source_metadata = excluded.source_metadata
            """,
            (
                values["run_id"],
                values["collector_id"],
                values["source_id"],
                values["organization"],
                values["started_at"],
                values["completed_at"],
                values["status"],
                values["pages_attempted"],
                values["records_encountered"],
                values["records_collected"],
                values["records_skipped"],
                values["issue_count"],
                values["resume_cursor"],
                _dump_json(values["source_metadata"]),
            ),
        )

    def get(self, run_id: UUID) -> CollectionRun | None:
        row = self._connection.execute(
            "SELECT * FROM collection_runs WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()
        return _collection_run_from_row(row) if row is not None else None

    def list_recent(self, limit: int = 20) -> list[CollectionRun]:
        _validate_limit(limit)
        rows = self._connection.execute(
            """
            SELECT * FROM collection_runs
            ORDER BY completed_at DESC, started_at DESC, run_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_collection_run_from_row(row) for row in rows]

    def list_by_organization(
        self,
        organization: str,
        limit: int = 20,
    ) -> list[CollectionRun]:
        _validate_limit(limit)
        rows = self._connection.execute(
            """
            SELECT * FROM collection_runs
            WHERE organization = ?
            ORDER BY completed_at DESC, started_at DESC, run_id DESC
            LIMIT ?
            """,
            (organization, limit),
        ).fetchall()
        return [_collection_run_from_row(row) for row in rows]


class SQLiteHiringUnitOfWork:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._connection: sqlite3.Connection | None = None
        self._committed = False

    def __enter__(self) -> SQLiteHiringUnitOfWork:
        if self._connection is not None:
            raise RuntimeError("unit of work is already active")
        try:
            self._connection = self._database.connect()
            self._connection.execute("BEGIN")
        except sqlite3.Error as error:
            self._connection = None
            raise PersistenceError(
                "SQLite transaction could not be started",
                code="sqlite_transaction_start_failed",
                metadata={"sqlite_error": type(error).__name__},
            ) from error
        self._committed = False
        self.job_postings = SQLiteJobPostingRepository(self._connection)
        self.evidence = SQLiteEvidenceRepository(self._connection)
        self.collection_runs = SQLiteCollectionRunRepository(self._connection)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connection is None:
            return
        try:
            if exc_type is not None or not self._committed:
                self._connection.rollback()
        finally:
            self._connection.close()
            self._connection = None
        if exc is not None and isinstance(exc, sqlite3.Error):
            raise PersistenceError(
                "SQLite persistence operation failed",
                code="sqlite_operation_failed",
                metadata={"sqlite_error": type(exc).__name__},
            ) from exc

    def commit(self) -> None:
        self._active_connection().commit()
        self._committed = True

    def rollback(self) -> None:
        self._active_connection().rollback()
        self._committed = False

    def _active_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("unit of work is not active")
        return self._connection


def _dump_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _validate_limit(limit: int) -> None:
    if limit < 1:
        raise ValueError("limit must be at least 1")


def _collection_run_from_row(row: sqlite3.Row) -> CollectionRun:
    return CollectionRun.model_validate(
        {
            "run_id": row["run_id"],
            "collector_id": row["collector_id"],
            "source_id": row["source_id"],
            "organization": row["organization"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "status": row["status"],
            "pages_attempted": row["pages_attempted"],
            "records_encountered": row["records_encountered"],
            "records_collected": row["records_collected"],
            "records_skipped": row["records_skipped"],
            "issue_count": row["issue_count"],
            "resume_cursor": row["resume_cursor"],
            "source_metadata": json.loads(row["source_metadata"]),
        }
    )


def _evidence_from_row(row: sqlite3.Row) -> Evidence:
    return Evidence.model_validate(
        {
            "evidence_id": row["evidence_id"],
            "source_url": row["source_url"],
            "source_type": row["source_type"],
            "source_title": row["source_title"],
            "retrieved_at": row["retrieved_at"],
            "source_excerpt": row["source_excerpt"],
            "raw_reference": row["raw_reference"],
            "collector_identity": row["collector_identity"],
            "provenance_metadata": json.loads(row["provenance_metadata"]),
        }
    )


def _job_posting_from_row(row: sqlite3.Row) -> JobPosting:
    return JobPosting.model_validate(
        {
            "job_id": row["job_id"],
            "organization": row["organization"],
            "source_job_id": row["source_job_id"],
            "title": row["title"],
            "description": row["description"],
            "location": row["location"],
            "country": row["country"],
            "business_unit": row["business_unit"],
            "capability_classifications": json.loads(
                row["capability_classifications"]
            ),
            "skills": json.loads(row["skills"]),
            "technologies": json.loads(row["technologies"]),
            "seniority_level": row["seniority_level"],
            "is_leadership": bool(row["is_leadership"]),
            "posted_date": row["posted_date"],
            "closing_date": row["closing_date"],
            "employment_type": row["employment_type"],
            "source_url": row["source_url"],
            "evidence_id": row["evidence_id"],
        }
    )
