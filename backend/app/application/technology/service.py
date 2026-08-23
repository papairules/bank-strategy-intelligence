from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol

from backend.app.application.hiring import EnrichmentField, EnrichmentSeniority, HiringEnrichmentResult
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

    def extract(self, organization: str) -> tuple[list[JobPosting], int, list[TechnologyObservation]]:
        jobs = self._read_service.list_jobs_for_analytics(organization)
        observations: list[TechnologyObservation] = []
        enriched_jobs = 0
        for job in jobs:
            evidence = self._read_service.get_evidence(job.evidence_id)
            if evidence is None:
                continue
            source_observations = self._source_observations(job, evidence)
            enrichment = self._read_service.get_latest_enrichment(job.job_id)
            if enrichment is None or enrichment.evidence_id != job.evidence_id:
                observations.extend(source_observations)
                continue
            enriched_jobs += 1
            enriched_observations = self._for_job(job, evidence, enrichment)
            observations.extend(self._merge_observations(source_observations, enriched_observations))
        return jobs, enriched_jobs, observations

    @staticmethod
    def _source_observations(job: JobPosting, evidence: Evidence) -> list[TechnologyObservation]:
        from backend.app.application.hiring.kg.source_technology import extract_source_technologies

        timestamp = datetime.combine(job.posted_date, datetime.min.time(), tzinfo=timezone.utc)
        return [
            TechnologyObservation(
                technology=match.matched_text,
                normalized_technology=match.technology,
                category=categorize_technology(match.technology),
                organization=job.organization,
                job_id=job.job_id,
                job_title=job.title,
                evidence_id=evidence.evidence_id,
                source_type=evidence.source_type,
                observation_date=job.posted_date,
                location=job.location,
                business_unit=job.business_unit,
                seniority=job.seniority_level or EnrichmentSeniority.UNKNOWN,
                confidence=1.0,
                support_classification="source_evidence",
                source_field=match.source_field,
                matched_text=match.matched_text,
                provenance=TechnologyProvenance(
                    provider="deterministic_source",
                    model="technology-taxonomy",
                    prompt_schema_version="source-technology-v1",
                    enrichment_timestamp=timestamp,
                ),
                support_references=[
                    TechnologySupportReference(
                        evidence_id=evidence.evidence_id,
                        excerpt=match.matched_text,
                    )
                ],
            )
            for match in extract_source_technologies(job.description)
        ]

    @staticmethod
    def _merge_observations(
        source_observations: list[TechnologyObservation],
        enrichment_observations: list[TechnologyObservation],
    ) -> list[TechnologyObservation]:
        source_by_key = {item.normalized_technology.casefold(): item for item in source_observations}
        merged: dict[str, TechnologyObservation] = {}
        for item in enrichment_observations:
            key = item.normalized_technology.casefold()
            existing = source_by_key.get(key)
            if existing is None:
                merged[key] = item
                continue
            merged[key] = existing.model_copy(
                update={
                    "support_classification": "multiple",
                    "support_references": TechnologyObservationService._unique_support_references(
                        [*existing.support_references, *item.support_references]
                    ),
                    "business_unit": item.business_unit,
                    "seniority": item.seniority,
                    "confidence": item.confidence,
                    "provenance": item.provenance,
                }
            )
        for item in source_observations:
            merged.setdefault(item.normalized_technology.casefold(), item)
        return list(merged.values())

    @staticmethod
    def _unique_support_references(references: list[TechnologySupportReference]) -> list[TechnologySupportReference]:
        unique: dict[tuple[object, str | None], TechnologySupportReference] = {}
        for reference in references:
            unique[(reference.evidence_id, reference.excerpt)] = reference
        return list(unique.values())

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
                    support_classification="ai_enrichment",
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
        return self._observation_service.extract(organization)[2]

    def analytics(self, organization: str) -> TechnologyAnalyticsResult:
        jobs, enriched_jobs, observations = self._observation_service.extract(organization)
        enriched_observations = [
            item for item in observations
            if item.support_classification in {"ai_enrichment", "multiple"}
        ]
        source_observations = [
            item for item in observations
            if item.support_classification in {"source_evidence", "multiple"}
        ]
        dates = [job.posted_date for job in jobs]
        source_jobs = {item.job_id for item in source_observations}
        snapshot = TechnologyIntelligenceSnapshot(
            organization=organization,
            total_jobs=len(jobs),
            enriched_jobs=enriched_jobs,
            technology_observation_count=len(enriched_observations),
            unique_technologies=len({item.normalized_technology for item in enriched_observations}),
            technology_coverage_percentage=(enriched_jobs / len(jobs) * 100 if jobs else 0),
            source_technology_jobs=len(source_jobs),
            source_technology_observation_count=len(source_observations),
            source_technology_coverage_percentage=(len(source_jobs) / len(jobs) * 100 if jobs else 0),
            observation_start=min(dates) if dates else None,
            observation_end=max(dates) if dates else None,
            generated_at=self._clock(),
        )
        return TechnologyAnalyticsResult(
            snapshot=snapshot,
            top_technologies=self._top_technologies(enriched_observations, enriched_jobs),
            categories=self._categories(enriched_observations),
            business_unit_technologies=self._cross_tab(enriched_observations, "business_unit"),
            geography_technologies=self._cross_tab(enriched_observations, "location"),
            seniority_technologies=self._cross_tab(enriched_observations, "seniority"),
        )

    @staticmethod
    def _reference(item: TechnologyObservation) -> TechnologyRecordReference:
        return TechnologyRecordReference(job_id=item.job_id, evidence_id=item.evidence_id)

    def _top_technologies(
        self,
        observations: list[TechnologyObservation],
        enriched_jobs: int,
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
                percentage_of_enriched_jobs=(job_count / enriched_jobs * 100 if enriched_jobs else 0),
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
