from typing import Protocol

from .models import StrategyProviderRequest, StrategyProviderResponse


class StrategyAgentProvider(Protocol):
    async def respond(self, request: StrategyProviderRequest) -> StrategyProviderResponse: ...
