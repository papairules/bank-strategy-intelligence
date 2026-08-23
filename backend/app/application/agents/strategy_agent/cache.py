from datetime import datetime, timedelta, timezone
from typing import Protocol

from backend.app.application.agents.strategy_agent.models import (
    StrategyAgentRequest,
    StrategyAgentResult,
)


def normalize_question_key(question: str) -> str:
    return " ".join(question.strip().casefold().split())


class StrategyAgentBoundary(Protocol):
    async def answer(self, request: StrategyAgentRequest) -> StrategyAgentResult: ...


class StrategyResearchCacheRepository(Protocol):
    def get(
        self,
        *,
        organization: str,
        question_key: str,
        time_horizon: str,
        provider: str,
        model: str,
        agent_version: str,
    ) -> tuple[StrategyAgentResult, str] | None: ...

    def save(
        self,
        *,
        organization: str,
        question_key: str,
        time_horizon: str,
        provider: str,
        model: str,
        agent_version: str,
        generated_at: str,
        result: StrategyAgentResult,
    ) -> None: ...


class CachedStrategyAgentService:
    """Wraps a live Strategy Agent with a persisted, TTL-bounded cache.

    Reuses a persisted result for an exact repeat of the same (organization,
    question, time_horizon) instead of re-running the live web-search
    pipeline, as long as the cached result is newer than `ttl`. A different
    question always triggers fresh, evidence-grounded research -- caching
    never substitutes an answer to a question that was not actually asked.
    """

    def __init__(
        self,
        inner: StrategyAgentBoundary,
        repository: StrategyResearchCacheRepository,
        *,
        provider: str,
        model: str,
        agent_version: str,
        ttl: timedelta,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._inner = inner
        self._repository = repository
        self._provider = provider
        self._model = model
        self._agent_version = agent_version
        self._ttl = ttl
        self._clock = clock

    async def answer(self, request: StrategyAgentRequest) -> StrategyAgentResult:
        question_key = normalize_question_key(request.question)
        time_horizon = request.time_horizon or ""
        cached = self._repository.get(
            organization=request.organization,
            question_key=question_key,
            time_horizon=time_horizon,
            provider=self._provider,
            model=self._model,
            agent_version=self._agent_version,
        )
        if cached is not None:
            result, generated_at_raw = cached
            generated_at = datetime.fromisoformat(generated_at_raw)
            if self._clock() - generated_at <= self._ttl:
                return result
        result = await self._inner.answer(request)
        self._repository.save(
            organization=request.organization,
            question_key=question_key,
            time_horizon=time_horizon,
            provider=self._provider,
            model=self._model,
            agent_version=self._agent_version,
            generated_at=self._clock().isoformat(),
            result=result,
        )
        return result
