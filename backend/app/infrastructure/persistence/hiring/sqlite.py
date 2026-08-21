from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import TracebackType
from uuid import UUID

from backend.app.domain.hiring import JobPosting
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


class SQLiteHiringUnitOfWork:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database
        self._connection: sqlite3.Connection | None = None
        self._committed = False

    def __enter__(self) -> SQLiteHiringUnitOfWork:
        if self._connection is not None:
            raise RuntimeError("unit of work is already active")
        self._connection = self._database.connect()
        self._connection.execute("BEGIN")
        self._committed = False
        self.job_postings = SQLiteJobPostingRepository(self._connection)
        self.evidence = SQLiteEvidenceRepository(self._connection)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._connection is None:
            return
        if exc_type is not None or not self._committed:
            self._connection.rollback()
        self._connection.close()
        self._connection = None

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
