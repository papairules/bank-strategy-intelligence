from typing import Protocol

from backend.app.application.agents.models import (
    AgentEvidenceDetailResult,
    EvidenceIdInput,
    EvidenceSearchInput,
    EvidenceTrace,
    OrganizationInput,
)
from backend.app.application.evidence import (
    EvidenceRecordFilters,
    EvidenceSummary,
    UnifiedEvidenceDetail,
    UnifiedEvidencePage,
)
from backend.app.application.strategy import StrategicSignalGenerationResult


class EvidenceBoundary(Protocol):
    def summary(self, organization: str) -> EvidenceSummary: ...
    def list_records(self, organization: str, filters: EvidenceRecordFilters) -> UnifiedEvidencePage: ...
    def get(self, evidence_id): ...


class StrategyBoundary(Protocol):
    def generate(self, organization: str) -> StrategicSignalGenerationResult: ...


class EvidenceAgentTools:
    def __init__(self, evidence: EvidenceBoundary, strategy: StrategyBoundary) -> None:
        self._evidence = evidence
        self._strategy = strategy

    def get_summary(self, request: OrganizationInput) -> EvidenceSummary:
        return self._evidence.summary(request.organization)

    def search(self, request: EvidenceSearchInput) -> UnifiedEvidencePage:
        return self._evidence.list_records(
            request.organization,
            EvidenceRecordFilters(
                search=request.search,
                source=request.source,
                enriched=request.enriched,
                technology=request.technology,
                capability=request.capability,
                location=request.location,
                job_id=request.job_id,
                limit=request.limit,
                offset=request.offset,
            ),
        )

    def get(self, request: EvidenceIdInput) -> AgentEvidenceDetailResult:
        detail = self._evidence.get(request.evidence_id)
        return AgentEvidenceDetailResult(found=detail is not None, detail=detail)

    def trace(self, request: EvidenceIdInput) -> EvidenceTrace:
        detail: UnifiedEvidenceDetail | None = self._evidence.get(request.evidence_id)
        if detail is None:
            return EvidenceTrace(
                found=False,
                evidence_id=request.evidence_id,
                limitations=["Evidence record not found."],
            )
        strategy = self._strategy.generate(detail.organization)
        cross_domain_ids = sorted(
            {
                signal.signal_id
                for signal in strategy.signals
                if request.evidence_id in signal.supporting_evidence_ids
            },
            key=str,
        )
        limitations = []
        if not detail.enrichment_present:
            limitations.append("No persisted enrichment uses this evidence.")
        if not detail.related_technology_signals:
            limitations.append("No technology signals currently cite this evidence.")
        if not cross_domain_ids:
            limitations.append("No cross-domain strategic signals currently cite this evidence.")
        return EvidenceTrace(
            found=True,
            evidence_id=detail.evidence_id,
            job_id=detail.job_id,
            organization=detail.organization,
            enrichment_present=detail.enrichment_present,
            enrichment_provider=detail.enrichment_provider,
            enrichment_model=detail.enrichment_model,
            enrichment_schema_version=detail.enrichment_schema_version,
            hiring_signals=detail.related_hiring_signals,
            technology_observations=sorted(
                {item.technology for item in detail.technology_observations},
                key=str.casefold,
            ),
            technology_signals=detail.related_technology_signals,
            cross_domain_signal_ids=cross_domain_ids,
            limitations=limitations,
        )
