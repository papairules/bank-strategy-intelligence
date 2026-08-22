from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from backend.app.application.hiring.enrichment import (
    EnrichmentFailureCode,
    HiringEnrichmentError,
    HiringEnrichmentResult,
    source_content_hash,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence


class BatchEnrichmentStatus(StrEnum):
    PLANNED = "planned"
    DEFERRED_LIMIT = "deferred_limit"
    ENRICHED = "enriched"
    SKIPPED_EXISTING = "skipped_existing"
    SKIPPED_NO_EVIDENCE = "skipped_no_evidence"
    SKIPPED_EVIDENCE_MISMATCH = "skipped_evidence_mismatch"
    SKIPPED_UNUSABLE_EVIDENCE = "skipped_unusable_evidence"
    FAILED_VALIDATION = "failed_validation"
    FAILED_PROVIDER = "failed_provider"
    FAILED_PERSISTENCE = "failed_persistence"


class BatchEnrichmentIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_schema_version: str = Field(min_length=1)


class HiringBatchEnrichmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1, max_length=200)
    max_jobs: int = Field(default=5, ge=1, le=25)
    dry_run: bool = True
    continue_on_error: bool = True

    @model_validator(mode="after")
    def reject_blank_organization(self):
        if not self.organization.strip():
            raise ValueError("organization must contain non-whitespace text")
        return self


class HiringBatchJobOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    evidence_id: UUID
    title: str
    status: BatchEnrichmentStatus
    failure_code: str | None = None
    message: str | None = None
    diagnostic_metadata: dict[str, JsonValue] = Field(default_factory=dict, exclude=True)


class HiringBatchEnrichmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    dry_run: bool
    configured_max_jobs: int
    discovered_jobs: int
    eligible_jobs: int
    planned_jobs: int
    attempted_jobs: int
    enriched_jobs: int
    existing_enrichment_skips: int
    no_evidence_skips: int
    evidence_mismatch_skips: int
    unusable_evidence_skips: int
    failed_jobs: int
    deferred_jobs: int
    stopped_early: bool
    outcomes: list[HiringBatchJobOutcome]

    @model_validator(mode="after")
    def validate_execution_counts(self):
        if self.discovered_jobs != len(self.outcomes):
            raise ValueError("discovered_jobs must match per-job outcomes")
        if self.attempted_jobs != self.enriched_jobs + self.failed_jobs:
            raise ValueError("attempted_jobs must equal enriched and failed outcomes")
        classified = (
            self.eligible_jobs
            + self.existing_enrichment_skips
            + self.no_evidence_skips
            + self.evidence_mismatch_skips
            + self.unusable_evidence_skips
        )
        if classified != self.discovered_jobs:
            raise ValueError("eligibility classifications must cover discovered jobs")
        return self


class BatchReadBoundary(Protocol):
    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]: ...
    def get_evidence(self, evidence_id: UUID) -> Evidence | None: ...


class BatchEnrichmentBoundary(Protocol):
    async def enrich(self, posting: JobPosting, evidence: Evidence) -> HiringEnrichmentResult: ...


class BatchPersistenceBoundary(Protocol):
    def has_current(self, *, job_id: UUID, evidence_id: UUID, provider: str, model: str, prompt_schema_version: str, source_content_hash: str) -> bool: ...
    def save(self, enrichment: HiringEnrichmentResult) -> None: ...


class HiringBatchEnrichmentService:
    def __init__(
        self,
        read_service: BatchReadBoundary,
        enrichment_service: BatchEnrichmentBoundary,
        persistence_service: BatchPersistenceBoundary,
        identity: BatchEnrichmentIdentity,
    ) -> None:
        self._read = read_service
        self._enrichment = enrichment_service
        self._persistence = persistence_service
        self._identity = identity

    async def execute(self, request: HiringBatchEnrichmentRequest) -> HiringBatchEnrichmentResult:
        jobs = sorted(
            self._read.list_jobs_for_analytics(request.organization),
            key=lambda job: (job.posted_date, str(job.job_id)),
        )
        outcomes: list[HiringBatchJobOutcome] = []
        eligible: list[tuple[JobPosting, Evidence]] = []
        for job in jobs:
            evidence = self._read.get_evidence(job.evidence_id)
            if evidence is None:
                outcomes.append(self._outcome(job, BatchEnrichmentStatus.SKIPPED_NO_EVIDENCE))
                continue
            if evidence.evidence_id != job.evidence_id:
                outcomes.append(self._outcome(job, BatchEnrichmentStatus.SKIPPED_EVIDENCE_MISMATCH))
                continue
            if not self._usable(job, evidence):
                outcomes.append(self._outcome(job, BatchEnrichmentStatus.SKIPPED_UNUSABLE_EVIDENCE))
                continue
            if self._persistence.has_current(
                job_id=job.job_id,
                evidence_id=evidence.evidence_id,
                provider=self._identity.provider,
                model=self._identity.model,
                prompt_schema_version=self._identity.prompt_schema_version,
                source_content_hash=source_content_hash(job),
            ):
                outcomes.append(self._outcome(job, BatchEnrichmentStatus.SKIPPED_EXISTING))
                continue
            eligible.append((job, evidence))

        selected = eligible[: request.max_jobs]
        deferred = eligible[request.max_jobs :]
        if request.dry_run:
            outcomes.extend(self._outcome(job, BatchEnrichmentStatus.PLANNED) for job, _ in selected)
            outcomes.extend(self._outcome(job, BatchEnrichmentStatus.DEFERRED_LIMIT) for job, _ in deferred)
            return self._result(request, jobs, eligible, outcomes, attempted=0, stopped=False)

        attempted = 0
        stopped = False
        for index, (job, evidence) in enumerate(selected):
            attempted += 1
            try:
                enrichment = await self._enrichment.enrich(job, evidence)
                if enrichment.job_id != job.job_id or enrichment.evidence_id != evidence.evidence_id:
                    raise HiringEnrichmentError(
                        EnrichmentFailureCode.VALIDATION_FAILURE,
                        "Validated enrichment identity did not match its source job and evidence.",
                    )
                self._persistence.save(enrichment)
                outcomes.append(self._outcome(job, BatchEnrichmentStatus.ENRICHED))
            except HiringEnrichmentError as error:
                outcomes.append(self._enrichment_failure(job, error))
                if not request.continue_on_error:
                    stopped = True
                    deferred = selected[index + 1 :] + deferred
                    break
            except Exception:
                outcomes.append(self._outcome(job, BatchEnrichmentStatus.FAILED_PERSISTENCE, "persistence_error", "Validated enrichment could not be persisted."))
                if not request.continue_on_error:
                    stopped = True
                    deferred = selected[index + 1 :] + deferred
                    break
        outcomes.extend(self._outcome(job, BatchEnrichmentStatus.DEFERRED_LIMIT) for job, _ in deferred)
        return self._result(request, jobs, eligible, outcomes, attempted=attempted, stopped=stopped)

    @staticmethod
    def _usable(job: JobPosting, evidence: Evidence) -> bool:
        return any(value is not None and value.strip() for value in (job.description, evidence.source_excerpt))

    @staticmethod
    def _outcome(job: JobPosting, status: BatchEnrichmentStatus, failure_code: str | None = None, message: str | None = None, diagnostic_metadata: dict[str, JsonValue] | None = None) -> HiringBatchJobOutcome:
        return HiringBatchJobOutcome(job_id=job.job_id, evidence_id=job.evidence_id, title=job.title, status=status, failure_code=failure_code, message=message, diagnostic_metadata=diagnostic_metadata or {})

    @classmethod
    def _enrichment_failure(cls, job: JobPosting, error: HiringEnrichmentError) -> HiringBatchJobOutcome:
        validation_codes = {EnrichmentFailureCode.EMPTY_EVIDENCE, EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT, EnrichmentFailureCode.VALIDATION_FAILURE}
        status = BatchEnrichmentStatus.FAILED_VALIDATION if error.code in validation_codes else BatchEnrichmentStatus.FAILED_PROVIDER
        message = "Enrichment validation failed." if status == BatchEnrichmentStatus.FAILED_VALIDATION else "Enrichment provider request failed."
        return cls._outcome(
            job,
            status,
            error.code.value,
            message,
            diagnostic_metadata=error.metadata,
        )

    @staticmethod
    def _result(request, jobs, eligible, outcomes, *, attempted: int, stopped: bool) -> HiringBatchEnrichmentResult:
        count = lambda status: sum(item.status == status for item in outcomes)
        return HiringBatchEnrichmentResult(
            organization=request.organization,
            dry_run=request.dry_run,
            configured_max_jobs=request.max_jobs,
            discovered_jobs=len(jobs),
            eligible_jobs=len(eligible),
            planned_jobs=min(len(eligible), request.max_jobs),
            attempted_jobs=attempted,
            enriched_jobs=count(BatchEnrichmentStatus.ENRICHED),
            existing_enrichment_skips=count(BatchEnrichmentStatus.SKIPPED_EXISTING),
            no_evidence_skips=count(BatchEnrichmentStatus.SKIPPED_NO_EVIDENCE),
            evidence_mismatch_skips=count(BatchEnrichmentStatus.SKIPPED_EVIDENCE_MISMATCH),
            unusable_evidence_skips=count(BatchEnrichmentStatus.SKIPPED_UNUSABLE_EVIDENCE),
            failed_jobs=count(BatchEnrichmentStatus.FAILED_VALIDATION) + count(BatchEnrichmentStatus.FAILED_PROVIDER) + count(BatchEnrichmentStatus.FAILED_PERSISTENCE),
            deferred_jobs=count(BatchEnrichmentStatus.DEFERRED_LIMIT),
            stopped_early=stopped,
            outcomes=outcomes,
        )
