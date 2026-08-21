from typing import Protocol
from uuid import UUID

from backend.app.application.evidence.models import (
    EvidenceRecordFilters,
    EvidenceSignalReference,
    EvidenceSourceDistribution,
    EvidenceSummary,
    EvidenceTechnologyObservationReference,
    UnifiedEvidenceDetail,
    UnifiedEvidencePage,
    UnifiedEvidenceRecord,
)
from backend.app.application.hiring import (
    HiringEnrichmentResult,
    HiringSignalGenerationResult,
)
from backend.app.application.technology import (
    TechnologyObservation,
    TechnologySignalGenerationResult,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence


class UnifiedEvidenceReadBoundary(Protocol):
    def list_jobs_for_analytics(self, organization: str) -> list[JobPosting]: ...
    def list_all_jobs(self) -> list[JobPosting]: ...
    def get_evidence(self, evidence_id: UUID) -> Evidence | None: ...
    def get_latest_enrichment(self, job_id: UUID) -> HiringEnrichmentResult | None: ...


class HiringSignalBoundary(Protocol):
    def generate(self, organization: str) -> HiringSignalGenerationResult: ...


class TechnologyObservationBoundary(Protocol):
    def observations(self, organization: str) -> list[TechnologyObservation]: ...


class TechnologySignalBoundary(Protocol):
    def generate(self, organization: str) -> TechnologySignalGenerationResult: ...


class UnifiedEvidenceService:
    def __init__(
        self,
        read_service: UnifiedEvidenceReadBoundary,
        hiring_signals: HiringSignalBoundary,
        technology_observations: TechnologyObservationBoundary,
        technology_signals: TechnologySignalBoundary,
    ) -> None:
        self._read_service = read_service
        self._hiring_signals = hiring_signals
        self._technology_observations = technology_observations
        self._technology_signals = technology_signals

    def summary(self, organization: str) -> EvidenceSummary:
        records = self._records(organization)
        jobs = self._read_service.list_jobs_for_analytics(organization)
        dates = [job.posted_date for job in jobs]
        source_counts: dict[tuple[str, object], int] = {}
        for record in records:
            key = (record.source, record.source_type)
            source_counts[key] = source_counts.get(key, 0) + 1
        return EvidenceSummary(
            organization=organization,
            total_evidence_records=len(records),
            total_jobs=len(jobs),
            jobs_with_evidence=len({record.job_id for record in records}),
            evidence_coverage=self._percentage(len({record.job_id for record in records}), len(jobs)),
            enriched_evidence_count=sum(record.enrichment_present for record in records),
            enrichment_coverage=self._percentage(sum(record.enrichment_present for record in records), len(records)),
            evidence_supporting_hiring_signals=sum(bool(record.related_hiring_signals) for record in records),
            evidence_supporting_technology_observations=sum(record.related_technology_observation_count > 0 for record in records),
            evidence_supporting_technology_signals=sum(bool(record.related_technology_signals) for record in records),
            source_distribution=[EvidenceSourceDistribution(source=source, source_type=source_type, evidence_count=count) for (source, source_type), count in sorted(source_counts.items(), key=lambda item: (item[0][0].casefold(), str(item[0][1])))],
            observation_start=min(dates) if dates else None,
            observation_end=max(dates) if dates else None,
            generated_at=max((record.captured_at for record in records), default=self._generated_at(organization)),
        )

    def list_records(self, organization: str, filters: EvidenceRecordFilters) -> UnifiedEvidencePage:
        records = self._records(organization)
        if filters.search:
            needle = filters.search.casefold()
            records = [record for record in records if needle in " ".join((record.job_title, record.job_location, record.evidence_preview or "", " ".join(record.technologies), " ".join(record.capabilities))).casefold()]
        if filters.source:
            needle = filters.source.casefold()
            records = [record for record in records if needle in record.source.casefold()]
        if filters.enriched is not None:
            records = [record for record in records if record.enrichment_present is filters.enriched]
        if filters.technology:
            needle = filters.technology.casefold()
            records = [record for record in records if any(needle in value.casefold() for value in record.technologies)]
        if filters.capability:
            needle = filters.capability.casefold()
            records = [record for record in records if any(needle in value.casefold() for value in record.capabilities)]
        if filters.location:
            needle = filters.location.casefold()
            records = [record for record in records if needle in record.job_location.casefold()]
        if filters.job_id:
            records = [record for record in records if record.job_id == filters.job_id]
        total = len(records)
        items = records[filters.offset : filters.offset + filters.limit]
        return UnifiedEvidencePage(items=items, total=total, limit=filters.limit, offset=filters.offset, returned_count=len(items))

    def records_for_intelligence(self, organization: str) -> list[UnifiedEvidenceRecord]:
        return self._records(organization)

    def get(
        self,
        organization: str,
        evidence_id: UUID,
    ) -> UnifiedEvidenceDetail | None:
        job = next(
            (
                item
                for item in self._read_service.list_jobs_for_analytics(organization)
                if item.evidence_id == evidence_id
            ),
            None,
        )
        if job is None:
            return None
        evidence = self._read_service.get_evidence(evidence_id)
        if evidence is None:
            return None
        context = self._context(job.organization)
        record = self._record(job, evidence, context)
        enrichment = self._read_service.get_latest_enrichment(job.job_id)
        observations = context["observations"].get(evidence_id, [])
        return UnifiedEvidenceDetail(
            **record.model_dump(),
            source_excerpt=evidence.source_excerpt,
            raw_reference=evidence.raw_reference,
            collector_identity=evidence.collector_identity,
            provenance_metadata=evidence.provenance_metadata,
            enrichment_limitations=enrichment.limitations if enrichment else [],
            technology_observations=[EvidenceTechnologyObservationReference(technology=item.normalized_technology, category=item.category, confidence=item.confidence, support_excerpt=item.support_references[0].excerpt if item.support_references else None) for item in observations],
        )

    def _records(self, organization: str) -> list[UnifiedEvidenceRecord]:
        context = self._context(organization)
        records = []
        for job in self._read_service.list_jobs_for_analytics(organization):
            evidence = self._read_service.get_evidence(job.evidence_id)
            if evidence is not None:
                records.append(self._record(job, evidence, context))
        return sorted(records, key=lambda item: (-item.observed_at.toordinal(), item.job_title.casefold(), str(item.evidence_id)))

    def _context(self, organization: str):
        hiring = self._hiring_signals.generate(organization)
        technology_observations = self._technology_observations.observations(organization)
        technology = self._technology_signals.generate(organization)
        hiring_by_evidence: dict[UUID, list[EvidenceSignalReference]] = {}
        for generated in hiring.signals:
            reference = EvidenceSignalReference(signal_id=generated.signal.signal_id, signal_type=generated.signal.signal_type, title=generated.title)
            for evidence_id in generated.signal.supporting_evidence_ids:
                hiring_by_evidence.setdefault(evidence_id, []).append(reference)
        observations_by_evidence: dict[UUID, list[TechnologyObservation]] = {}
        for observation in technology_observations:
            existing = observations_by_evidence.setdefault(observation.evidence_id, [])
            if not any(
                item.job_id == observation.job_id
                and item.normalized_technology == observation.normalized_technology
                for item in existing
            ):
                existing.append(observation)
        technology_by_evidence: dict[UUID, list[EvidenceSignalReference]] = {}
        for signal in technology.signals:
            reference = EvidenceSignalReference(signal_id=signal.signal_id, signal_type=signal.signal_type.value, title=signal.title)
            for evidence_id in signal.supporting_evidence_ids:
                technology_by_evidence.setdefault(evidence_id, []).append(reference)
        for mapping in (hiring_by_evidence, technology_by_evidence):
            for evidence_id, references in mapping.items():
                mapping[evidence_id] = sorted(set(references), key=lambda item: (item.signal_type, item.title, str(item.signal_id)))
        return {"hiring": hiring_by_evidence, "observations": observations_by_evidence, "technology": technology_by_evidence, "generated_at": hiring.generated_at}

    def _record(self, job: JobPosting, evidence: Evidence, context) -> UnifiedEvidenceRecord:
        enrichment = self._read_service.get_latest_enrichment(job.job_id)
        observations = context["observations"].get(evidence.evidence_id, [])
        source = evidence.provenance_metadata.get("source_system")
        if not isinstance(source, str) or not source.strip():
            source = evidence.collector_identity
        return UnifiedEvidenceRecord(
            evidence_id=evidence.evidence_id,
            organization=job.organization,
            source=source,
            source_type=evidence.source_type,
            source_url=evidence.source_url,
            captured_at=evidence.retrieved_at,
            observed_at=job.posted_date,
            job_id=job.job_id,
            job_title=job.title,
            job_location=job.location,
            business_unit=enrichment.business_unit if enrichment else job.business_unit,
            enrichment_present=enrichment is not None,
            enrichment_provider=enrichment.model_metadata.provider if enrichment else None,
            enrichment_model=enrichment.model_metadata.model if enrichment else None,
            enrichment_schema_version=enrichment.model_metadata.prompt_schema_version if enrichment else None,
            application_confidence=enrichment.confidence if enrichment else None,
            technologies=enrichment.technologies if enrichment else [],
            capabilities=[item.value for item in enrichment.capability_classifications] if enrichment else [],
            skills=enrichment.skills if enrichment else [],
            seniority=enrichment.seniority_level if enrichment else None,
            related_hiring_signals=context["hiring"].get(evidence.evidence_id, []),
            related_technology_observation_count=len(observations),
            related_technology_signals=context["technology"].get(evidence.evidence_id, []),
            evidence_preview=self._preview(evidence.source_excerpt),
        )

    def _generated_at(self, organization: str):
        return self._hiring_signals.generate(organization).generated_at

    @staticmethod
    def _preview(value: str | None) -> str | None:
        if value is None:
            return None
        compact = " ".join(value.split())
        return compact if len(compact) <= 280 else f"{compact[:277]}..."

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        return round(numerator / denominator * 100, 2) if denominator else 0.0
