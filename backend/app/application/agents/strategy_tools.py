from typing import Protocol

from backend.app.application.agents.models import AgentStrategyContext, OrganizationInput
from backend.app.application.strategy import StrategicSignalGenerationResult


class StrategyBoundary(Protocol):
    def generate(self, organization: str) -> StrategicSignalGenerationResult: ...


class StrategyAgentTools:
    def __init__(self, strategy: StrategyBoundary) -> None:
        self._strategy = strategy

    def get_signals(self, request: OrganizationInput) -> StrategicSignalGenerationResult:
        return self._strategy.generate(request.organization)

    def get_context(self, request: OrganizationInput) -> AgentStrategyContext:
        result = self._strategy.generate(request.organization)
        context = result.coverage_context
        return AgentStrategyContext(
            organization=request.organization,
            generated_at=result.generated_at,
            observation_start=context.observation_start,
            observation_end=context.observation_end,
            hiring_coverage=context.hiring_evidence_coverage,
            enrichment_coverage=context.enrichment_coverage,
            evidence_coverage=context.hiring_evidence_coverage,
            hiring_signal_count=context.hiring_signal_count,
            technology_observation_count=context.technology_observation_count,
            technology_signal_count=context.technology_signal_count,
            cross_domain_signal_count=len(result.signals),
            limitations=result.limitations,
            coverage_context=context,
        )
