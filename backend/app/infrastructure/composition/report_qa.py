from collections.abc import Callable

from openai import OpenAI

from backend.app.application.agents.supervisor_agent.report_qa import ReportQAService
from backend.app.config import HiringSettings


def create_report_qa_service(
    settings: HiringSettings | None = None,
    *,
    client_factory: Callable[[], OpenAI] | None = None,
) -> ReportQAService:
    resolved = settings or HiringSettings()
    factory = client_factory or (
        lambda: OpenAI(api_key=resolved.openai_api_key or "missing-api-key")
    )
    return ReportQAService(
        client_factory=factory,
        model=resolved.openai_model,
        enabled=resolved.report_qa_enabled,
    )
