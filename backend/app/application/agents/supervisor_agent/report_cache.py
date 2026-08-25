from datetime import datetime, timedelta, timezone
from typing import Protocol

from backend.app.application.agents.strategy_agent.cache import normalize_question_key

from .runtime import SupervisorReportRequest, SupervisorReportResult


class SupervisorReportBoundary(Protocol):
    async def generate_report(self, request: SupervisorReportRequest) -> SupervisorReportResult: ...


class SupervisorReportCacheRepository(Protocol):
    def get(
        self,
        *,
        organization: str,
        question_key: str,
        time_horizon: str,
        provider: str,
        model: str,
    ) -> tuple[SupervisorReportResult, str] | None: ...

    def save(
        self,
        *,
        organization: str,
        question_key: str,
        time_horizon: str,
        provider: str,
        model: str,
        generated_at: str,
        result: SupervisorReportResult,
    ) -> None: ...


class CachedSupervisorReportService:
    """Wraps a live Supervisor report generator with a persisted, TTL-bounded cache.

    Reuses a persisted report for an exact repeat of the same (organization,
    question, time_horizon) instead of re-running Strategy Agent research, the
    knowledge graph rebuild, hiring signal regeneration, and Supervisor
    synthesis, as long as the cached result is newer than `ttl`. A different
    question always triggers a fresh report -- caching never substitutes an
    answer to a question that was not actually asked. This is what keeps an
    auto-loading report page cheap on repeat visits.
    """

    def __init__(
        self,
        inner: SupervisorReportBoundary,
        repository: SupervisorReportCacheRepository,
        *,
        provider: str,
        model: str,
        ttl: timedelta,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self._inner = inner
        self._repository = repository
        self._provider = provider
        self._model = model
        self._ttl = ttl
        self._clock = clock

    async def generate_report(self, request: SupervisorReportRequest) -> SupervisorReportResult:
        question_key = normalize_question_key(request.question or "")
        time_horizon = request.time_horizon or ""
        cached = self._repository.get(
            organization=request.organization,
            question_key=question_key,
            time_horizon=time_horizon,
            provider=self._provider,
            model=self._model,
        )
        if cached is not None:
            result, generated_at_raw = cached
            generated_at = datetime.fromisoformat(generated_at_raw)
            if self._clock() - generated_at <= self._ttl:
                return result
        result = await self._inner.generate_report(request)
        self._repository.save(
            organization=request.organization,
            question_key=question_key,
            time_horizon=time_horizon,
            provider=self._provider,
            model=self._model,
            generated_at=self._clock().isoformat(),
            result=result,
        )
        return result
