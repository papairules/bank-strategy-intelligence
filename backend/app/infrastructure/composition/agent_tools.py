from dataclasses import dataclass

from backend.app.application.agents import (
    AgentToolRegistry,
    EvidenceAgentTools,
    HiringAgentTools,
    StrategyAgentTools,
    TechnologyAgentTools,
)
from backend.app.application.evidence import UnifiedEvidenceService
from backend.app.application.hiring import (
    HiringAnalyticsService,
    HiringDashboardService,
    HiringSignalService,
)
from backend.app.application.strategy import CrossDomainStrategicSignalService
from backend.app.application.technology import (
    TechnologyAnalyticsService,
    TechnologyObservationService,
    TechnologySignalService,
)
from backend.app.config import HiringSettings
from backend.app.infrastructure.composition.hiring_read import create_hiring_read_service


@dataclass(frozen=True)
class AgentIntelligenceTools:
    hiring: HiringAgentTools
    technology: TechnologyAgentTools
    evidence: EvidenceAgentTools
    strategy: StrategyAgentTools
    registry: AgentToolRegistry


def create_agent_intelligence_tools(
    settings: HiringSettings | None = None,
) -> AgentIntelligenceTools:
    read_service = create_hiring_read_service(settings)
    hiring_dashboard = HiringDashboardService(read_service)
    technology_analytics = TechnologyAnalyticsService(
        TechnologyObservationService(read_service)
    )
    technology_signals = TechnologySignalService(technology_analytics)
    unified_evidence = UnifiedEvidenceService(
        read_service,
        HiringSignalService(HiringAnalyticsService(read_service)),
        technology_analytics,
        technology_signals,
    )
    strategy = CrossDomainStrategicSignalService(
        hiring_dashboard,
        technology_analytics,
        technology_signals,
        unified_evidence,
    )
    return AgentIntelligenceTools(
        hiring=HiringAgentTools(read_service, hiring_dashboard),
        technology=TechnologyAgentTools(technology_analytics, technology_signals),
        evidence=EvidenceAgentTools(unified_evidence, strategy),
        strategy=StrategyAgentTools(strategy),
        registry=AgentToolRegistry(),
    )
