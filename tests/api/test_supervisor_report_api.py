from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_supervisor_app_service
from backend.app.application.agents.supervisor_agent import (
    SupervisorRuntimeError,
    SupervisorRuntimeFailureCode,
)
from backend.app.main import app


class FakeSupervisorService:
    async def generate_report(self, request):
        raise SupervisorRuntimeError(
            SupervisorRuntimeFailureCode.ORGANIZATION_SCOPE_MISMATCH,
            "The question targets Goldman Sachs, but the current data scope is Wells Fargo.",
        )


def test_supervisor_company_mismatch_returns_clear_422():
    app.dependency_overrides[get_supervisor_app_service] = lambda: FakeSupervisorService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/agents/supervisor/report",
                json={"organization": "Wells Fargo", "question": "Report on Goldman Sachs"},
            )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "organization_scope_mismatch"
        assert "Wells Fargo" in response.json()["detail"]["message"]
    finally:
        app.dependency_overrides.clear()


def test_supervisor_report_endpoint_is_in_openapi():
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/agents/supervisor/report"]["post"]
    assert operation["tags"] == ["Supervisor Agent"]


def test_report_qa_endpoint_is_additive_and_in_openapi():
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/agents/supervisor/report" in paths
    assert "/api/v1/agents/supervisor/report/answer" in paths
