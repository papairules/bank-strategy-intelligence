from dataclasses import dataclass

from pydantic import BaseModel

from backend.app.application.agents.models import (
    AgentCollectionContext,
    AgentEvidenceDetailResult,
    AgentJobIntelligence,
    AgentJobSearchResult,
    AgentStrategyContext,
    AgentTechnologyAnalytics,
    AgentTechnologyObservationSearchResult,
    AgentTechnologySummary,
    AgentToolDomain,
    CollectionContextInput,
    EvidenceIdInput,
    EvidenceSearchInput,
    EvidenceTrace,
    JobIdInput,
    JobSearchInput,
    OrganizationInput,
    TechnologyObservationSearchInput,
)
from backend.app.application.evidence import EvidenceSummary, UnifiedEvidencePage
from backend.app.application.hiring import (
    HiringOrganizationSummary,
    HiringSignalGenerationResult,
)
from backend.app.application.strategy import StrategicSignalGenerationResult
from backend.app.application.technology import TechnologySignalGenerationResult


@dataclass(frozen=True)
class AgentToolDefinition:
    name: str
    domain: AgentToolDomain
    description: str
    read_only: bool
    input_model: type[BaseModel]
    output_model: type[BaseModel]


class AgentToolRegistry:
    def __init__(self) -> None:
        definitions = (
            AgentToolDefinition("hiring.get_summary", AgentToolDomain.HIRING, "Return deterministic hiring coverage, analytics, and signal summary.", True, OrganizationInput, HiringOrganizationSummary),
            AgentToolDefinition("hiring.search_jobs", AgentToolDomain.HIRING, "Search compact normalized job records with bounded pagination.", True, JobSearchInput, AgentJobSearchResult),
            AgentToolDefinition("hiring.get_job_intelligence", AgentToolDomain.HIRING, "Return compact normalized job and persisted enrichment intelligence.", True, JobIdInput, AgentJobIntelligence),
            AgentToolDefinition("hiring.get_signals", AgentToolDomain.HIRING, "Return existing deterministic hiring signals and limitations.", True, OrganizationInput, HiringSignalGenerationResult),
            AgentToolDefinition("hiring.get_collection_context", AgentToolDomain.HIRING, "Return recent collection-run audit context.", True, CollectionContextInput, AgentCollectionContext),
            AgentToolDefinition("technology.get_summary", AgentToolDomain.TECHNOLOGY, "Return technology coverage and observation summary.", True, OrganizationInput, AgentTechnologySummary),
            AgentToolDefinition("technology.get_analytics", AgentToolDomain.TECHNOLOGY, "Return existing deterministic technology analytics.", True, OrganizationInput, AgentTechnologyAnalytics),
            AgentToolDefinition("technology.search_observations", AgentToolDomain.TECHNOLOGY, "Search evidence-linked technology observations with bounded pagination.", True, TechnologyObservationSearchInput, AgentTechnologyObservationSearchResult),
            AgentToolDefinition("technology.get_signals", AgentToolDomain.TECHNOLOGY, "Return existing technology signals or explicit suppression context.", True, OrganizationInput, TechnologySignalGenerationResult),
            AgentToolDefinition("evidence.get_summary", AgentToolDomain.EVIDENCE, "Return deterministic evidence coverage and provenance summary.", True, OrganizationInput, EvidenceSummary),
            AgentToolDefinition("evidence.search", AgentToolDomain.EVIDENCE, "Search compact unified evidence records with bounded pagination.", True, EvidenceSearchInput, UnifiedEvidencePage),
            AgentToolDefinition("evidence.get", AgentToolDomain.EVIDENCE, "Return a detailed authoritative evidence record and linked intelligence.", True, EvidenceIdInput, AgentEvidenceDetailResult),
            AgentToolDefinition("evidence.trace", AgentToolDomain.EVIDENCE, "Return a compact evidence-to-intelligence relationship trace.", True, EvidenceIdInput, EvidenceTrace),
            AgentToolDefinition("strategy.get_signals", AgentToolDomain.STRATEGY, "Return existing deterministic cross-domain signals or suppression context.", True, OrganizationInput, StrategicSignalGenerationResult),
            AgentToolDefinition("strategy.get_context", AgentToolDomain.STRATEGY, "Return read-only cross-domain coverage and availability context without conclusions.", True, OrganizationInput, AgentStrategyContext),
        )
        names = [definition.name for definition in definitions]
        if len(names) != len(set(names)):
            raise ValueError("Agent tool names must be unique.")
        self._definitions = definitions

    def list(self) -> tuple[AgentToolDefinition, ...]:
        return self._definitions

    def get(self, name: str) -> AgentToolDefinition | None:
        return next((item for item in self._definitions if item.name == name), None)
