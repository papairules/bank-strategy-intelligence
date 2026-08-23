from collections import defaultdict
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.application.evidence import EvidenceSummary, UnifiedEvidenceRecord
from backend.app.application.hiring import HiringAnalyticsResult, HiringSignalGenerationResult
from backend.app.application.strategy.models import (
    CrossDomainStrategicSignal,
    IntelligenceDomain,
    StrategicCoverageContext,
    StrategicSignalGenerationResult,
    StrategicSignalProvenance,
    StrategicSignalThresholds,
    StrategicSignalType,
)
from backend.app.application.technology import TechnologyAnalyticsResult, TechnologySignalGenerationResult


class HiringIntelligenceBoundary(Protocol):
    def analytics(self, organization: str) -> HiringAnalyticsResult: ...
    def signals(self, organization: str) -> HiringSignalGenerationResult: ...


class TechnologyAnalyticsBoundary(Protocol):
    def analytics(self, organization: str) -> TechnologyAnalyticsResult: ...


class TechnologySignalBoundary(Protocol):
    def generate(self, organization: str) -> TechnologySignalGenerationResult: ...


class UnifiedEvidenceBoundary(Protocol):
    def summary(self, organization: str) -> EvidenceSummary: ...
    def records_for_intelligence(self, organization: str) -> list[UnifiedEvidenceRecord]: ...


class CrossDomainStrategicSignalService:
    def __init__(
        self,
        hiring: HiringIntelligenceBoundary,
        technology_analytics: TechnologyAnalyticsBoundary,
        technology_signals: TechnologySignalBoundary,
        evidence: UnifiedEvidenceBoundary,
        thresholds: StrategicSignalThresholds | None = None,
    ) -> None:
        self._hiring = hiring
        self._technology_analytics = technology_analytics
        self._technology_signals = technology_signals
        self._evidence = evidence
        self._thresholds = thresholds or StrategicSignalThresholds()

    def generate(self, organization: str) -> StrategicSignalGenerationResult:
        hiring_analytics = self._hiring.analytics(organization)
        hiring_signals = self._hiring.signals(organization)
        technology = self._technology_analytics.analytics(organization)
        technology_signals = self._technology_signals.generate(organization)
        intelligence = getattr(self._evidence, "intelligence", None)
        if intelligence is None:
            evidence_summary = self._evidence.summary(organization)
            evidence_records = self._evidence.records_for_intelligence(organization)
        else:
            evidence_summary, evidence_records = intelligence(
                organization,
                hiring=hiring_signals,
                technology=technology_signals,
            )
        context = StrategicCoverageContext(
            total_jobs=evidence_summary.total_jobs,
            jobs_with_evidence=evidence_summary.jobs_with_evidence,
            hiring_evidence_coverage=self._ratio(evidence_summary.jobs_with_evidence, evidence_summary.total_jobs),
            enriched_jobs=technology.snapshot.enriched_jobs,
            enrichment_coverage=self._ratio(technology.snapshot.enriched_jobs, technology.snapshot.total_jobs),
            hiring_signal_count=len(hiring_signals.signals),
            technology_observation_count=technology.snapshot.technology_observation_count,
            technology_signal_count=len(technology_signals.signals),
            observation_start=hiring_analytics.snapshot.observation_start,
            observation_end=hiring_analytics.snapshot.observation_end,
        )
        limitations = self._result_limitations(context)
        if not self._passes_global_gates(context):
            return StrategicSignalGenerationResult(
                organization=organization,
                generated_at=hiring_analytics.snapshot.generated_at,
                coverage_context=context,
                limitations=limitations,
            )

        evidence_by_job = {record.job_id: record.evidence_id for record in evidence_records}
        signals = [
            *self._capability_alignments(organization, hiring_analytics, technology, hiring_signals, technology_signals, evidence_by_job, context),
            *self._geographic_alignments(organization, hiring_analytics, technology, hiring_signals, technology_signals, evidence_by_job, context),
            *self._business_unit_alignments(organization, evidence_records, hiring_signals, technology_signals, context),
            *self._leadership_alignments(organization, hiring_analytics, technology, hiring_signals, technology_signals, evidence_by_job, context),
            *self._signal_clusters(organization, hiring_signals, technology_signals, evidence_records, context),
        ]
        signals.sort(key=lambda signal: (signal.signal_type.value, signal.primary_subject.casefold(), tuple(signal.related_subjects), str(signal.signal_id)))
        return StrategicSignalGenerationResult(
            organization=organization,
            generated_at=hiring_analytics.snapshot.generated_at,
            coverage_context=context,
            signals=signals,
            limitations=limitations,
        )

    def _capability_alignments(self, organization, hiring, technology, hiring_signals, technology_signals, evidence_by_job, context):
        results = []
        for capability in hiring.capability.capabilities:
            hiring_jobs = {item.job_id for item in capability.contributing_records}
            hiring_concentration = self._unit(capability.percentage_of_classified_jobs / 100)
            for tech in technology.top_technologies:
                technology_jobs = {item.job_id for item in tech.contributing_records}
                technology_concentration = self._unit(tech.percentage_of_enriched_jobs / 100)
                results.extend(self._alignment(
                    organization, StrategicSignalType.CAPABILITY_TECHNOLOGY_ALIGNMENT,
                    capability.capability, [tech.technology], hiring_jobs, technology_jobs,
                    hiring_concentration, technology_concentration,
                    f"Observed overlap between {capability.capability} hiring and {tech.technology}",
                    f"Within the observed hiring evidence, {capability.capability} classifications overlap with {tech.technology} observations across {{count}} independently contributing job records. This relationship is observational and does not establish a strategy, initiative, or causal link.",
                    hiring_signals, technology_signals, evidence_by_job, context,
                ))
        return results

    def _geographic_alignments(self, organization, hiring, technology, hiring_signals, technology_signals, evidence_by_job, context):
        results = []
        for geography in hiring.geographic.by_city:
            hiring_jobs = {item.job_id for item in geography.contributing_records}
            hiring_concentration = self._unit(geography.percentage_of_total / 100)
            for tech in technology.top_technologies:
                technology_jobs = {item.job_id for item in tech.contributing_records}
                results.extend(self._alignment(
                    organization, StrategicSignalType.GEOGRAPHIC_TECHNOLOGY_ALIGNMENT,
                    geography.value, [tech.technology], hiring_jobs, technology_jobs,
                    hiring_concentration, self._unit(tech.percentage_of_enriched_jobs / 100),
                    f"Observed {tech.technology} hiring overlap in {geography.value}",
                    f"Current evidence shows overlap between hiring activity in {geography.value} and {tech.technology} observations across {{count}} independently contributing job records. This does not prove location-level adoption or organizational intent.",
                    hiring_signals, technology_signals, evidence_by_job, context,
                ))
        return results

    def _business_unit_alignments(self, organization, records, hiring_signals, technology_signals, context):
        grouped: dict[tuple[str, str], set[UUID]] = defaultdict(set)
        unit_jobs: dict[str, set[UUID]] = defaultdict(set)
        evidence_by_job = {record.job_id: record.evidence_id for record in records}
        for record in records:
            if record.business_unit:
                unit_jobs[record.business_unit].add(record.job_id)
                for technology in record.technologies:
                    grouped[(record.business_unit, technology)].add(record.job_id)
        results = []
        for (unit, technology), technology_jobs in grouped.items():
            hiring_jobs = unit_jobs[unit]
            results.extend(self._alignment(
                organization, StrategicSignalType.BUSINESS_UNIT_TECHNOLOGY_ALIGNMENT,
                unit, [technology], hiring_jobs, technology_jobs,
                self._ratio(len(hiring_jobs), context.total_jobs), self._ratio(len(technology_jobs), context.enriched_jobs),
                f"Observed {technology} hiring overlap in {unit}",
                f"Among sufficiently supported hiring records, {technology} observations overlap with {unit} across {{count}} independently contributing jobs. This evidence does not establish business-unit deployment or intent.",
                hiring_signals, technology_signals, evidence_by_job, context,
            ))
        return results

    def _leadership_alignments(self, organization, hiring, technology, hiring_signals, technology_signals, evidence_by_job, context):
        hiring_jobs = {item.job_id for item in hiring.seniority.leadership_contributing_records}
        results = []
        for tech in technology.top_technologies:
            technology_jobs = {item.job_id for item in tech.contributing_records}
            results.extend(self._alignment(
                organization, StrategicSignalType.LEADERSHIP_TECHNOLOGY_ALIGNMENT,
                "leadership hiring", [tech.technology], hiring_jobs, technology_jobs,
                self._unit(hiring.seniority.leadership_percentage / 100), self._unit(tech.percentage_of_enriched_jobs / 100),
                f"Observed leadership hiring overlap with {tech.technology}",
                f"The observed sample contains leadership-classified hiring and {tech.technology} observations across {{count}} independently contributing jobs. This does not establish leadership intent or technology direction.",
                hiring_signals, technology_signals, evidence_by_job, context,
            ))
        return results

    def _signal_clusters(self, organization, hiring_signals, technology_signals, records, context):
        evidence_to_job = {record.evidence_id: record.job_id for record in records}
        results = []
        for hiring in hiring_signals.signals:
            hiring_evidence = set(hiring.signal.supporting_evidence_ids)
            hiring_jobs = {evidence_to_job[item] for item in hiring_evidence if item in evidence_to_job}
            for technology in technology_signals.signals:
                technology_evidence = set(technology.supporting_evidence_ids)
                technology_jobs = {evidence_to_job[item] for item in technology_evidence if item in evidence_to_job}
                results.extend(self._alignment(
                    organization, StrategicSignalType.HIRING_TECHNOLOGY_CLUSTER,
                    hiring.title, [technology.title], hiring_jobs, technology_jobs,
                    hiring.score.strength, technology.strength,
                    "Observed overlap between hiring and technology signals",
                    "Within the observed hiring evidence, an existing hiring signal overlaps with an existing technology signal across {count} independently contributing jobs. This higher-order pattern remains observational and non-causal.",
                    hiring_signals, technology_signals, {value: key for key, value in evidence_to_job.items()}, context,
                    related_hiring_ids=[hiring.signal.signal_id], related_technology_ids=[technology.signal_id],
                ))
        return results

    def _alignment(self, organization, signal_type, primary, related, hiring_jobs, technology_jobs, hiring_concentration, technology_concentration, title, summary, hiring_signals, technology_signals, evidence_by_job, context, related_hiring_ids=None, related_technology_ids=None):
        overlap = hiring_jobs & technology_jobs
        thresholds = self._thresholds
        if (
            len(hiring_jobs) < thresholds.minimum_hiring_contributors
            or len(technology_jobs) < thresholds.minimum_technology_contributors
            or len(overlap) < thresholds.minimum_unique_cross_domain_contributors
            or hiring_concentration < thresholds.minimum_domain_concentration
            or technology_concentration < thresholds.minimum_domain_concentration
        ):
            return []
        evidence_ids = sorted({evidence_by_job[job_id] for job_id in overlap if job_id in evidence_by_job}, key=str)
        if len(evidence_ids) < thresholds.minimum_unique_cross_domain_contributors:
            return []
        related_hiring_ids = related_hiring_ids or self._related_hiring_ids(hiring_signals, evidence_ids)
        related_technology_ids = related_technology_ids or self._related_technology_ids(technology_signals, evidence_ids)
        evidence_coverage = self._unit(len(evidence_ids) / len(overlap))
        overlap_strength = self._unit(len(overlap) / max(len(hiring_jobs), len(technology_jobs)))
        strength = self._unit((hiring_concentration + technology_concentration + overlap_strength) / 3)
        sample_sufficiency = self._unit(len(overlap) / (thresholds.minimum_unique_cross_domain_contributors * 2))
        confidence = self._unit((context.enrichment_coverage + evidence_coverage + sample_sufficiency) / 3)
        identity = "|".join((organization, signal_type.value, primary, *sorted(related), str(context.observation_start), str(context.observation_end), thresholds.configuration_version))
        return [CrossDomainStrategicSignal(
            signal_id=uuid5(NAMESPACE_URL, f"cross-domain:{identity}"), organization=organization,
            signal_type=signal_type, title=title, summary=summary.format(count=len(overlap)),
            primary_subject=primary, related_subjects=sorted(set(related)),
            domains_involved=[IntelligenceDomain.HIRING, IntelligenceDomain.TECHNOLOGY],
            observation_start=context.observation_start, observation_end=context.observation_end,
            strength=strength, confidence=confidence, evidence_coverage=evidence_coverage,
            hiring_contributor_count=len(hiring_jobs), technology_contributor_count=len(technology_jobs),
            unique_contributing_job_ids=sorted(overlap, key=str), supporting_evidence_ids=evidence_ids,
            related_hiring_signal_ids=sorted(set(related_hiring_ids), key=str),
            related_technology_signal_ids=sorted(set(related_technology_ids), key=str),
            limitations=self._signal_limitations(context),
            provenance=StrategicSignalProvenance(configuration_version=thresholds.configuration_version),
        )]

    @staticmethod
    def _related_hiring_ids(result, evidence_ids):
        evidence = set(evidence_ids)
        return [item.signal.signal_id for item in result.signals if evidence & set(item.signal.supporting_evidence_ids)]

    @staticmethod
    def _related_technology_ids(result, evidence_ids):
        evidence = set(evidence_ids)
        return [item.signal_id for item in result.signals if evidence & set(item.supporting_evidence_ids)]

    def _passes_global_gates(self, context):
        thresholds = self._thresholds
        period_days = (context.observation_end - context.observation_start).days if context.observation_start and context.observation_end else 0
        return (
            context.total_jobs >= thresholds.minimum_total_jobs
            and context.enriched_jobs >= thresholds.minimum_enriched_jobs
            and context.enrichment_coverage >= thresholds.minimum_enrichment_coverage
            and context.technology_observation_count >= thresholds.minimum_technology_contributors
            and period_days >= thresholds.minimum_observation_days
        )

    def _result_limitations(self, context):
        limitations = []
        if context.total_jobs < self._thresholds.minimum_total_jobs: limitations.append("The observed hiring sample is below the configured minimum.")
        if context.enriched_jobs < self._thresholds.minimum_enriched_jobs: limitations.append("The enriched hiring sample is below the configured minimum for cross-domain signals.")
        if context.enrichment_coverage < self._thresholds.minimum_enrichment_coverage: limitations.append("Technology enrichment coverage is below the configured reliability threshold; broader cross-domain claims are withheld.")
        if context.technology_observation_count < self._thresholds.minimum_technology_contributors: limitations.append("Too few technology observations are available for independent cross-domain support.")
        if not context.observation_start or not context.observation_end or (context.observation_end - context.observation_start).days < self._thresholds.minimum_observation_days: limitations.append("The observation period is shorter than the configured minimum.")
        limitations.extend(self._signal_limitations(context))
        return list(dict.fromkeys(limitations))

    def _signal_limitations(self, context):
        limitations = []
        if context.enrichment_coverage < 1: limitations.append("Technology enrichment covers only a subset of observed hiring records.")
        if self._thresholds.single_source_data: limitations.append("Evidence currently derives from a single public hiring source.")
        limitations.extend(["Cross-domain overlap is observational and does not establish causation or organizational intent.", "Hiring evidence does not prove production technology deployment."])
        return limitations

    @staticmethod
    def _ratio(numerator, denominator): return numerator / denominator if denominator else 0.0
    @staticmethod
    def _unit(value): return max(0.0, min(1.0, value))
