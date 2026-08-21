from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import get_evidence_agent_service
from backend.app.api.v1.agents.schemas import (
    EvidenceAgentAnswerRequest,
    EvidenceAgentAnswerResponse,
)
from backend.app.application.agents.evidence_agent import (
    EvidenceAgentError,
    EvidenceAgentFailureCode,
    EvidenceAgentRequest,
    EvidenceAgentService,
)


router = APIRouter(prefix="/agents/evidence", tags=["Evidence Agent"])
EvidenceAgent = Annotated[EvidenceAgentService, Depends(get_evidence_agent_service)]

_FAILURE_STATUS = {
    EvidenceAgentFailureCode.DISABLED: status.HTTP_503_SERVICE_UNAVAILABLE,
    EvidenceAgentFailureCode.INVALID_REQUEST: status.HTTP_422_UNPROCESSABLE_ENTITY,
    EvidenceAgentFailureCode.AUTHENTICATION: status.HTTP_503_SERVICE_UNAVAILABLE,
    EvidenceAgentFailureCode.PERMISSIONS: status.HTTP_503_SERVICE_UNAVAILABLE,
    EvidenceAgentFailureCode.QUOTA: status.HTTP_429_TOO_MANY_REQUESTS,
    EvidenceAgentFailureCode.TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    EvidenceAgentFailureCode.PROVIDER_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    EvidenceAgentFailureCode.INVALID_PROVIDER_REQUEST: status.HTTP_502_BAD_GATEWAY,
    EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT: status.HTTP_502_BAD_GATEWAY,
    EvidenceAgentFailureCode.INVALID_TOOL_REQUEST: status.HTTP_502_BAD_GATEWAY,
    EvidenceAgentFailureCode.TOOL_EXECUTION_LIMIT: status.HTTP_502_BAD_GATEWAY,
    EvidenceAgentFailureCode.CITATION_VALIDATION: status.HTTP_502_BAD_GATEWAY,
    EvidenceAgentFailureCode.PROVENANCE_VALIDATION: status.HTTP_502_BAD_GATEWAY,
}


@router.post("/answer", response_model=EvidenceAgentAnswerResponse)
async def answer_evidence_question(
    request: EvidenceAgentAnswerRequest,
    service: EvidenceAgent,
) -> EvidenceAgentAnswerResponse:
    try:
        result = await service.answer(
            EvidenceAgentRequest(
                organization=request.organization,
                question=request.question,
            )
        )
    except EvidenceAgentError as error:
        raise HTTPException(
            status_code=_FAILURE_STATUS[error.code],
            detail={"code": error.code.value, "message": _safe_message(error.code)},
        ) from error
    return EvidenceAgentAnswerResponse.model_validate(result.model_dump())


def _safe_message(code: EvidenceAgentFailureCode) -> str:
    if code == EvidenceAgentFailureCode.DISABLED:
        return "The Evidence Agent is currently disabled."
    if code == EvidenceAgentFailureCode.QUOTA:
        return "The Evidence Agent is temporarily rate limited."
    if code == EvidenceAgentFailureCode.TIMEOUT:
        return "The Evidence Agent request timed out."
    if code in {
        EvidenceAgentFailureCode.CITATION_VALIDATION,
        EvidenceAgentFailureCode.PROVENANCE_VALIDATION,
        EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT,
        EvidenceAgentFailureCode.INVALID_PROVIDER_REQUEST,
        EvidenceAgentFailureCode.INVALID_TOOL_REQUEST,
        EvidenceAgentFailureCode.TOOL_EXECUTION_LIMIT,
    }:
        return "The Evidence Agent could not validate a grounded answer."
    return "The Evidence Agent is temporarily unavailable."
