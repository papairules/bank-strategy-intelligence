from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from backend.app.application.hiring import (
    EnrichmentField,
    EnrichmentSeniority,
    HiringEnrichmentResult,
)
from backend.app.domain.technology_keywords import find_technology_excerpt
from backend.app.application.technology.models import (
    BusinessUnitTechnologyAggregate,
    GeographyTechnologyAggregate,
    SeniorityTechnologyAggregate,
    TechnologyAnalyticsResult,
    TechnologyCategory,
    TechnologyCategoryAggregate,
    TechnologyIntelligenceSnapshot,
    TechnologyObservation,
    TechnologyProvenance,
    TechnologyRecordReference,
    TechnologySupportReference,
    TopTechnologyAggregate,
)
from backend.app.application.technology.normalization import (
    categorize_technology,
    normalize_technology,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence


class TechnologyReadBoundary(Protocol):
    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]: ...
    def get_latest_enrichment(self, job_id) -> HiringEnrichmentResult | None: ...
    def get_evidence(self, evidence_id) -> Evidence | None: ...


class TechnologyObservationService:
    def __init__(self, read_service: TechnologyReadBoundary) -> None:
        self._read_service = read_service

    def extract(
        self, organization: str
    ) -> tuple[list[JobPosting], int, int, list[TechnologyObservation]]:
        jobs = self._read_service.list_jobs_for_analytics(organization)
        observations: list[TechnologyObservation] = []
        enriched_jobs = 0
        jobs_with_signal = 0
        now = datetime.now(timezone.utc)
        for job in jobs:
            evidence = self._read_service.get_evidence(job.evidence_id)
            if evidence is None:
                continue
            enrichment = self._read_service.get_latest_enrichment(job.job_id)
            job_observations: list[TechnologyObservation] = []
            seen: set[str] = set()
            if enrichment is not None and enrichment.evidence_id == job.evidence_id:
                enriched_jobs += 1
                job_observations = self._for_job(job, evidence, enrichment)
                observations.extend(job_observations)
                seen.update(item.normalized_technology.casefold() for item in job_observations)
            persisted_source = self._for_job_persisted_source(job, evidence, seen, now)
            observations.extend(persisted_source)
            if job_observations or persisted_source:
                jobs_with_signal += 1
        return jobs, enriched_jobs, jobs_with_signal, observations

    @staticmethod
    def _for_job(
        job: JobPosting,
        evidence: Evidence,
        enrichment: HiringEnrichmentResult,
    ) -> list[TechnologyObservation]:
        observations: list[TechnologyObservation] = []
        seen: set[str] = set()
        confidence = enrichment.field_confidences.get(
            EnrichmentField.TECHNOLOGIES,
            enrichment.confidence,
        )
        for technology in enrichment.technologies:
            normalized = normalize_technology(technology)
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            seen.add(key)
            support = [
                TechnologySupportReference(
                    evidence_id=item.evidence_id,
                    excerpt=item.excerpt,
                )
                for item in enrichment.field_support
                if item.field == EnrichmentField.TECHNOLOGIES
                and normalize_technology(item.value).casefold() == key
                and item.evidence_id == evidence.evidence_id
            ]
            if not support:
                support = [TechnologySupportReference(evidence_id=evidence.evidence_id)]
            observations.append(
                TechnologyObservation(
                    technology=technology,
                    normalized_technology=normalized,
                    category=categorize_technology(normalized),
                    organization=job.organization,
                    job_id=job.job_id,
                    job_title=job.title,
                    evidence_id=evidence.evidence_id,
                    source_type=evidence.source_type,
                    observation_date=job.posted_date,
                    location=job.location,
                    business_unit=enrichment.business_unit or job.business_unit,
                    seniority=enrichment.seniority_level,
                    confidence=confidence,
                    provenance=TechnologyProvenance(
                        provider=enrichment.model_metadata.provider,
                        model=enrichment.model_metadata.model,
                        prompt_schema_version=enrichment.model_metadata.prompt_schema_version,
                        enrichment_timestamp=enrichment.model_metadata.enrichment_timestamp,
                    ),
                    support_references=support,
                )
            )
        return observations

    # Deterministic, zero-cost technology signal (backend/app/domain/technology_keywords.py):
    # a curated keyword match against title/description, distinct from the LLM
    # enrichment path above. No per-value grounding excerpt is guaranteed the
    # way enrichment's field_support is, so this is tagged with its own
    # provider/confidence tier rather than presented as equivalent evidence.
    KEYWORD_MATCH_PROVIDER = "keyword_match"
    KEYWORD_MATCH_MODEL = "technology_keywords_v1"
    KEYWORD_MATCH_PROMPT_SCHEMA_VERSION = "persisted_source_keyword_match_v1"
    KEYWORD_MATCH_CONFIDENCE = 0.6

    @classmethod
    def _for_job_persisted_source(
        cls,
        job: JobPosting,
        evidence: Evidence,
        seen: set[str],
        now: datetime,
    ) -> list[TechnologyObservation]:
        observations: list[TechnologyObservation] = []
        for technology in job.technologies:
            normalized = normalize_technology(technology)
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            seen.add(key)
            excerpt = find_technology_excerpt(technology, job.title, job.description)
            observations.append(
                TechnologyObservation(
                    technology=technology,
                    normalized_technology=normalized,
                    category=categorize_technology(normalized),
                    organization=job.organization,
                    job_id=job.job_id,
                    job_title=job.title,
                    evidence_id=evidence.evidence_id,
                    source_type=evidence.source_type,
                    observation_date=job.posted_date,
                    location=job.location,
                    business_unit=job.business_unit,
                    seniority=EnrichmentSeniority.UNKNOWN,
                    confidence=cls.KEYWORD_MATCH_CONFIDENCE,
                    provenance=TechnologyProvenance(
                        provider=cls.KEYWORD_MATCH_PROVIDER,
                        model=cls.KEYWORD_MATCH_MODEL,
                        prompt_schema_version=cls.KEYWORD_MATCH_PROMPT_SCHEMA_VERSION,
                        enrichment_timestamp=now,
                    ),
                    support_references=[
                        TechnologySupportReference(evidence_id=evidence.evidence_id, excerpt=excerpt)
                    ],
                )
            )
        return observations


class TechnologyAnalyticsService:
    def __init__(
        self,
        observation_service: TechnologyObservationService,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._observation_service = observation_service
        self._clock = clock

    def observations(self, organization: str) -> list[TechnologyObservation]:
        return self._observation_service.extract(organization)[3]

    def analytics(self, organization: str) -> TechnologyAnalyticsResult:
        jobs, enriched_jobs, jobs_with_signal, observations = self._observation_service.extract(organization)
        dates = [job.posted_date for job in jobs]
        snapshot = TechnologyIntelligenceSnapshot(
            organization=organization,
            total_jobs=len(jobs),
            enriched_jobs=enriched_jobs,
            technology_observation_count=len(observations),
            unique_technologies=len({item.normalized_technology for item in observations}),
            technology_coverage_percentage=(enriched_jobs / len(jobs) * 100 if jobs else 0),
            jobs_with_technology_signal=jobs_with_signal,
            technology_signal_coverage_percentage=(jobs_with_signal / len(jobs) * 100 if jobs else 0),
            observation_start=min(dates) if dates else None,
            observation_end=max(dates) if dates else None,
            generated_at=self._clock(),
        )
        return TechnologyAnalyticsResult(
            snapshot=snapshot,
            top_technologies=self._top_technologies(observations, enriched_jobs, jobs_with_signal),
            categories=self._categories(observations),
            business_unit_technologies=self._cross_tab(observations, "business_unit"),
            geography_technologies=self._cross_tab(observations, "location"),
            seniority_technologies=self._cross_tab(observations, "seniority"),
        )

    @staticmethod
    def _reference(item: TechnologyObservation) -> TechnologyRecordReference:
        return TechnologyRecordReference(job_id=item.job_id, evidence_id=item.evidence_id)

    def _top_technologies(
        self,
        observations: list[TechnologyObservation],
        enriched_jobs: int,
        jobs_with_signal: int,
    ) -> list[TopTechnologyAggregate]:
        groups: dict[str, list[TechnologyObservation]] = defaultdict(list)
        for item in observations:
            groups[item.normalized_technology].append(item)
        results = []
        for technology, items in groups.items():
            references = sorted({self._reference(item) for item in items}, key=lambda ref: str(ref.job_id))
            job_count = len({item.job_id for item in items})
            results.append(TopTechnologyAggregate(
                technology=technology,
                category=items[0].category,
                job_count=job_count,
                observation_count=len(items),
                # job_count can exceed enriched_jobs now that a technology may also be
                # observed via the persisted-source keyword match on jobs that were
                # never LLM-enriched; clamp rather than let the percentage exceed 100.
                percentage_of_enriched_jobs=(
                    min(job_count / enriched_jobs * 100, 100.0) if enriched_jobs else 0
                ),
                percentage_of_technology_classified_jobs=(
                    min(job_count / jobs_with_signal * 100, 100.0) if jobs_with_signal else 0
                ),
                evidence_count=len({item.evidence_id for item in items}),
                contributing_records=references,
            ))
        return sorted(results, key=lambda item: (-item.job_count, item.technology.casefold()))

    def _categories(self, observations: list[TechnologyObservation]) -> list[TechnologyCategoryAggregate]:
        groups: dict[TechnologyCategory, list[TechnologyObservation]] = defaultdict(list)
        for item in observations:
            groups[item.category].append(item)
        return sorted((TechnologyCategoryAggregate(
            category=category,
            unique_technology_count=len({item.normalized_technology for item in items}),
            observation_count=len(items),
            job_count=len({item.job_id for item in items}),
            contributing_records=sorted({self._reference(item) for item in items}, key=lambda ref: str(ref.job_id)),
        ) for category, items in groups.items()), key=lambda item: (-item.observation_count, item.category.value))

    def _cross_tab(self, observations: list[TechnologyObservation], field: str):
        groups: dict[tuple[object, str], list[TechnologyObservation]] = defaultdict(list)
        for item in observations:
            value = getattr(item, field)
            if value is not None and value != "unknown":
                groups[(value, item.normalized_technology)].append(item)
        rows = []
        model = {
            "business_unit": BusinessUnitTechnologyAggregate,
            "location": GeographyTechnologyAggregate,
            "seniority": SeniorityTechnologyAggregate,
        }[field]
        for (value, technology), items in groups.items():
            rows.append(model(**{
                field: value,
                "technology": technology,
                "job_count": len({item.job_id for item in items}),
                "contributing_records": sorted({self._reference(item) for item in items}, key=lambda ref: str(ref.job_id)),
            }))
        return sorted(rows, key=lambda item: (-item.job_count, item.technology.casefold()))
