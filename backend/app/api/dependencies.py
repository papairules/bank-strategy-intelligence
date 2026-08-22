from functools import lru_cache

from fastapi import Depends

from backend.app.application.evidence import UnifiedEvidenceService
from backend.app.application.agents.evidence_agent import EvidenceAgentService
from backend.app.application.agents.hiring_agent import HiringAgentAppService
from backend.app.application.agents.strategy_agent import IntegratedStrategyAgentService
from backend.app.application.hiring import HiringAnalyticsService, HiringSignalService
from backend.app.application.hiring import HiringDashboardService, HiringReadService
from backend.app.application.strategy import CrossDomainStrategicSignalService
from backend.app.application.technology import (
    TechnologyAnalyticsService,
    TechnologyObservationService,
    TechnologySignalService,
)
from backend.app.infrastructure.composition.hiring_read import (
    create_hiring_read_service,
)
from backend.app.infrastructure.composition.evidence_agent import (
    create_evidence_agent_service,
)
from backend.app.infrastructure.composition.hiring_agent import (
    create_hiring_agent_service,
)
from backend.app.infrastructure.composition.strategy_agent import (
    create_strategy_agent_service,
)


@lru_cache
def get_hiring_read_service() -> HiringReadService:
    return create_hiring_read_service()


@lru_cache
def get_evidence_agent_service() -> EvidenceAgentService:
    return create_evidence_agent_service()


@lru_cache
def get_strategy_agent_service() -> IntegratedStrategyAgentService:
    return create_strategy_agent_service()


@lru_cache
def get_hiring_agent_service() -> HiringAgentAppService:
    return create_hiring_agent_service()


def get_hiring_dashboard_service(
    read_service: HiringReadService = Depends(get_hiring_read_service),
) -> HiringDashboardService:
    return HiringDashboardService(read_service)


def get_technology_analytics_service(
    read_service: HiringReadService = Depends(get_hiring_read_service),
) -> TechnologyAnalyticsService:
    return TechnologyAnalyticsService(TechnologyObservationService(read_service))


def get_technology_signal_service(
    analytics_service: TechnologyAnalyticsService = Depends(
        get_technology_analytics_service
    ),
) -> TechnologySignalService:
    return TechnologySignalService(analytics_service)


def get_unified_evidence_service(
    read_service: HiringReadService = Depends(get_hiring_read_service),
    technology_analytics: TechnologyAnalyticsService = Depends(
        get_technology_analytics_service
    ),
    technology_signals: TechnologySignalService = Depends(
        get_technology_signal_service
    ),
) -> UnifiedEvidenceService:
    return UnifiedEvidenceService(
        read_service,
        HiringSignalService(HiringAnalyticsService(read_service)),
        technology_analytics,
        technology_signals,
    )


def get_cross_domain_strategic_signal_service(
    hiring: HiringDashboardService = Depends(get_hiring_dashboard_service),
    technology_analytics: TechnologyAnalyticsService = Depends(
        get_technology_analytics_service
    ),
    technology_signals: TechnologySignalService = Depends(
        get_technology_signal_service
    ),
    evidence: UnifiedEvidenceService = Depends(get_unified_evidence_service),
) -> CrossDomainStrategicSignalService:
    return CrossDomainStrategicSignalService(
        hiring,
        technology_analytics,
        technology_signals,
        evidence,
    )
