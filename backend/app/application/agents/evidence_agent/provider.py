from typing import Protocol

from .models import EvidenceAgentProviderRequest, EvidenceAgentProviderResponse


class EvidenceAgentProvider(Protocol):
    async def respond(self, request: EvidenceAgentProviderRequest) -> EvidenceAgentProviderResponse: ...
