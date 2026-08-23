from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import TracebackType
from uuid import UUID

from backend.app.application.agents.strategy_agent.models import StrategyAgentResult
from backend.app.application.hiring.observability import CollectionRun
from backend.app.application.hiring.enrichment import HiringEnrichmentResult
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

CREATE TABLE IF NOT EXISTS hiring_enrichments (
    job_id TEXT NOT NULL REFERENCES job_postings(job_id),
    evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_schema_version TEXT NOT NULL,
    source_content_hash TEXT NOT NULL,
    enrichment_timestamp TEXT NOT NULL,
    capability_classifications TEXT NOT NULL,
    skills TEXT NOT NULL,
    technologies TEXT NOT NULL,
    seniority_level TEXT NOT NULL,
    is_leadership INTEGER NOT NULL CHECK (is_leadership IN (0, 1)),
    business_unit TEXT,
    hiring_themes TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    model_confidence REAL NOT NULL CHECK (
        model_confidence >= 0 AND model_confidence <= 1
    ),
    field_confidences TEXT NOT NULL,
    field_support TEXT NOT NULL,
    limitations TEXT NOT NULL,
    provider_request_id TEXT,
    model_version TEXT,
    usage_metadata TEXT NOT NULL,
    PRIMARY KEY (
        job_id,
        evidence_id,
        provider,
        model,
        prompt_schema_version
    )
);

CREATE INDEX IF NOT EXISTS idx_hiring_enrichments_job_latest
    ON hiring_enrichments(job_id, enrichment_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_hiring_enrichments_evidence_id
    ON hiring_enrichments(evidence_id);

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

CREATE TABLE IF NOT EXISTS strategy_research_cache (
    organization TEXT NOT NULL,
    question_key TEXT NOT NULL,
    time_horizon TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    result_json TEXT NOT NULL,
    PRIMARY KEY (organization, question_key, time_horizon, provider, model, agent_version)
);

CREATE INDEX IF NOT EXISTS idx_strategy_research_cache_generated_at
    ON strategy_research_cache(organization, generated_at DESC);
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
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(hiring_enrichments)")
            }
            if "source_content_hash" not in columns:
                connection.execute(
                    "ALTER TABLE hiring_enrichments "
                    "ADD COLUMN source_content_hash TEXT NOT NULL DEFAULT ''"
                )

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
        location: str | None = None,
        capability: str | None = None,
        seniority: str | None = None,
        limit: int,
        offset: int,
    ) -> list[JobPosting]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        clauses, parameters = self._filters(
            organization=organization,
            country=country,
            employment_type=employment_type,
            location=location,
            capability=capability,
            seniority=seniority,
        )
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

    def count(
        self,
        *,
        organization: str | None,
        country: str | None = None,
        employment_type: EmploymentType | None = None,
        location: str | None = None,
        capability: str | None = None,
        seniority: str | None = None,
    ) -> int:
        clauses, parameters = self._filters(
            organization=organization,
            country=country,
            employment_type=employment_type,
            location=location,
            capability=capability,
            seniority=seniority,
        )
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = self._connection.execute(
            f"SELECT COUNT(*) AS count FROM job_postings {where_clause}",
            parameters,
        ).fetchone()
        return int(row["count"])

    @staticmethod
    def _filters(
        *,
        organization: str | None,
        country: str | None,
        employment_type: EmploymentType | None,
        location: str | None,
        capability: str | None,
        seniority: str | None,
    ) -> tuple[list[str], list[str]]:
        clauses: list[str] = []
        parameters: list[str] = []
        if organization is not None:
            clauses.append("organization = ?")
            parameters.append(organization)
        if country is not None:
            clauses.append("country = ?")
            parameters.append(country)
        if employment_type is not None:
            clauses.append("employment_type = ?")
            parameters.append(employment_type.value)
        if location is not None:
            clauses.append("LOWER(location) LIKE LOWER(?)")
            parameters.append(f"%{location}%")
        if capability is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(capability_classifications) "
                "WHERE LOWER(json_each.value) = LOWER(?))"
            )
            parameters.append(capability)
        if seniority is not None:
            clauses.append("seniority_level = ?")
            parameters.append(seniority)
        return clauses, parameters


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


class SQLiteHiringEnrichmentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, enrichment: HiringEnrichmentResult) -> None:
        values = enrichment.model_dump(mode="json")
        metadata = values["model_metadata"]
        self._connection.execute(
            """
            INSERT INTO hiring_enrichments (
                job_id, evidence_id, provider, model, prompt_schema_version,
                source_content_hash, enrichment_timestamp, capability_classifications, skills,
                technologies, seniority_level, is_leadership, business_unit,
                hiring_themes, confidence, model_confidence, field_confidences,
                field_support, limitations, provider_request_id, model_version,
                usage_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
                job_id, evidence_id, provider, model, prompt_schema_version
            ) DO UPDATE SET
                enrichment_timestamp = excluded.enrichment_timestamp,
                source_content_hash = excluded.source_content_hash,
                capability_classifications = excluded.capability_classifications,
                skills = excluded.skills,
                technologies = excluded.technologies,
                seniority_level = excluded.seniority_level,
                is_leadership = excluded.is_leadership,
                business_unit = excluded.business_unit,
                hiring_themes = excluded.hiring_themes,
                confidence = excluded.confidence,
                model_confidence = excluded.model_confidence,
                field_confidences = excluded.field_confidences,
                field_support = excluded.field_support,
                limitations = excluded.limitations,
                provider_request_id = excluded.provider_request_id,
                model_version = excluded.model_version,
                usage_metadata = excluded.usage_metadata
            """,
            (
                values["job_id"],
                values["evidence_id"],
                metadata["provider"],
                metadata["model"],
                metadata["prompt_schema_version"],
                values["source_content_hash"],
                metadata["enrichment_timestamp"],
                _dump_json(values["capability_classifications"]),
                _dump_json(values["skills"]),
                _dump_json(values["technologies"]),
                values["seniority_level"],
                int(values["is_leadership"]),
                values["business_unit"],
                _dump_json(values["hiring_themes"]),
                values["confidence"],
                metadata["model_confidence"],
                _dump_json(values["field_confidences"]),
                _dump_json(values["field_support"]),
                _dump_json(values["limitations"]),
                metadata["provider_request_id"],
                metadata["model_version"],
                _dump_json(metadata["usage_metadata"]),
            ),
        )

    def get_exact(
        self,
        *,
        job_id: UUID,
        evidence_id: UUID,
        provider: str,
        model: str,
        prompt_schema_version: str,
    ) -> HiringEnrichmentResult | None:
        row = self._connection.execute(
            """
            SELECT * FROM hiring_enrichments
            WHERE job_id = ? AND evidence_id = ? AND provider = ?
                AND model = ? AND prompt_schema_version = ?
            """,
            (
                str(job_id),
                str(evidence_id),
                provider,
                model,
                prompt_schema_version,
            ),
        ).fetchone()
        return _hiring_enrichment_from_row(row) if row is not None else None

    def get_latest(self, job_id: UUID) -> HiringEnrichmentResult | None:
        row = self._connection.execute(
            """
            SELECT * FROM hiring_enrichments
            WHERE job_id = ?
            ORDER BY enrichment_timestamp DESC, prompt_schema_version DESC,
                provider DESC, model DESC
            LIMIT 1
            """,
            (str(job_id),),
        ).fetchone()
        return _hiring_enrichment_from_row(row) if row is not None else None

    def list_by_job(self, job_id: UUID) -> list[HiringEnrichmentResult]:
        rows = self._connection.execute(
            """
            SELECT * FROM hiring_enrichments
            WHERE job_id = ?
            ORDER BY enrichment_timestamp DESC, prompt_schema_version DESC,
                provider DESC, model DESC
            """,
            (str(job_id),),
        ).fetchall()
        return [_hiring_enrichment_from_row(row) for row in rows]

    def list_by_organization(
        self,
        organization: str,
    ) -> list[HiringEnrichmentResult]:
        rows = self._connection.execute(
            """
            SELECT enrichment.*
            FROM hiring_enrichments AS enrichment
            JOIN job_postings AS job ON job.job_id = enrichment.job_id
            WHERE job.organization = ?
            ORDER BY enrichment.enrichment_timestamp DESC,
                enrichment.job_id, enrichment.prompt_schema_version DESC
            """,
            (organization,),
        ).fetchall()
        return [_hiring_enrichment_from_row(row) for row in rows]

    def exists(
        self,
        *,
        job_id: UUID,
        evidence_id: UUID,
        provider: str,
        model: str,
        prompt_schema_version: str,
        source_content_hash: str,
    ) -> bool:
        row = self._connection.execute(
            """
            SELECT 1 FROM hiring_enrichments
            WHERE job_id = ? AND evidence_id = ? AND provider = ?
                AND model = ? AND prompt_schema_version = ?
                AND source_content_hash = ?
            LIMIT 1
            """,
            (
                str(job_id),
                str(evidence_id),
                provider,
                model,
                prompt_schema_version,
                source_content_hash,
            ),
        ).fetchone()
        return row is not None

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
        self.enrichments = SQLiteHiringEnrichmentRepository(self._connection)
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


def _hiring_enrichment_from_row(row: sqlite3.Row) -> HiringEnrichmentResult:
    return HiringEnrichmentResult.model_validate(
        {
            "job_id": row["job_id"],
            "evidence_id": row["evidence_id"],
            "source_content_hash": row["source_content_hash"],
            "capability_classifications": json.loads(
                row["capability_classifications"]
            ),
            "skills": json.loads(row["skills"]),
            "technologies": json.loads(row["technologies"]),
            "seniority_level": row["seniority_level"],
            "is_leadership": bool(row["is_leadership"]),
            "business_unit": row["business_unit"],
            "hiring_themes": json.loads(row["hiring_themes"]),
            "confidence": row["confidence"],
            "field_confidences": json.loads(row["field_confidences"]),
            "field_support": json.loads(row["field_support"]),
            "limitations": json.loads(row["limitations"]),
            "model_metadata": {
                "provider": row["provider"],
                "model": row["model"],
                "prompt_schema_version": row["prompt_schema_version"],
                "provider_request_id": row["provider_request_id"],
                "model_version": row["model_version"],
                "usage_metadata": json.loads(row["usage_metadata"]),
                "enrichment_timestamp": row["enrichment_timestamp"],
                "model_confidence": row["model_confidence"],
            },
        }
    )


class SQLiteStrategyResearchCacheRepository:
    """Persists Strategy Agent research so repeated (organization, question,
    time_horizon) requests can be served without re-running the live web-search
    pipeline. Keyed by provider/model/agent_version too, so a model or agent
    upgrade naturally invalidates stale cached research."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get(
        self,
        *,
        organization: str,
        question_key: str,
        time_horizon: str,
        provider: str,
        model: str,
        agent_version: str,
    ) -> tuple[StrategyAgentResult, str] | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT generated_at, result_json FROM strategy_research_cache
                WHERE organization = ? AND question_key = ? AND time_horizon = ?
                  AND provider = ? AND model = ? AND agent_version = ?
                """,
                (organization, question_key, time_horizon, provider, model, agent_version),
            ).fetchone()
        if row is None:
            return None
        return StrategyAgentResult.model_validate_json(row["result_json"]), row["generated_at"]

    def get_latest_for_organization(
        self, organization: str
    ) -> tuple[StrategyAgentResult, str] | None:
        """Return the most recently generated cached research for this
        organization, regardless of which question produced it. Used to feed
        the knowledge graph with whatever Strategy Agent research already
        exists, without triggering a new live run."""
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT generated_at, result_json FROM strategy_research_cache
                WHERE organization = ?
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (organization,),
            ).fetchone()
        if row is None:
            return None
        return StrategyAgentResult.model_validate_json(row["result_json"]), row["generated_at"]

    def save(
        self,
        *,
        organization: str,
        question_key: str,
        time_horizon: str,
        provider: str,
        model: str,
        agent_version: str,
        generated_at: str,
        result: StrategyAgentResult,
    ) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO strategy_research_cache (
                    organization, question_key, time_horizon, provider, model,
                    agent_version, generated_at, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(organization, question_key, time_horizon, provider, model, agent_version)
                DO UPDATE SET
                    generated_at = excluded.generated_at,
                    result_json = excluded.result_json
                """,
                (
                    organization,
                    question_key,
                    time_horizon,
                    provider,
                    model,
                    agent_version,
                    generated_at,
                    result.model_dump_json(),
                ),
            )
            connection.commit()
