from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import (
    get_evidence_agent_service,
    get_hiring_agent_service,
    get_strategy_agent_service,
)
from backend.app.api.v1.agents.schemas import (
    EvidenceAgentAnswerRequest,
    EvidenceAgentAnswerResponse,
    HiringAgentAnswerRequest,
    HiringAgentAnswerResponse,
    StrategyAgentAnswerRequest,
    StrategyAgentAnswerResponse,
)
from backend.app.application.agents.strategy_agent import (
    StrategyAgentError,
    StrategyAgentFailureCode,
    StrategyAgentRequest,
    IntegratedStrategyAgentService,
)
from backend.app.application.agents.evidence_agent import (
    EvidenceAgentError,
    EvidenceAgentFailureCode,
    EvidenceAgentRequest,
    EvidenceAgentService,
)
from backend.app.application.agents.hiring_agent import (
    HiringAgentAppRequest,
    HiringAgentAppService,
    HiringAgentError,
    HiringAgentFailureCode,
)


router = APIRouter(prefix="/agents")
EvidenceAgent = Annotated[EvidenceAgentService, Depends(get_evidence_agent_service)]
StrategyAgent = Annotated[IntegratedStrategyAgentService, Depends(get_strategy_agent_service)]
HiringAgent = Annotated[HiringAgentAppService, Depends(get_hiring_agent_service)]

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


@router.post("/evidence/answer", response_model=EvidenceAgentAnswerResponse, tags=["Evidence Agent"])
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


_STRATEGY_FAILURE_STATUS = {
    StrategyAgentFailureCode.DISABLED: status.HTTP_503_SERVICE_UNAVAILABLE,
    StrategyAgentFailureCode.INVALID_REQUEST: status.HTTP_422_UNPROCESSABLE_ENTITY,
    StrategyAgentFailureCode.ORGANIZATION_SCOPE_MISMATCH: status.HTTP_422_UNPROCESSABLE_ENTITY,
    StrategyAgentFailureCode.AUTHENTICATION: status.HTTP_503_SERVICE_UNAVAILABLE,
    StrategyAgentFailureCode.PERMISSIONS: status.HTTP_503_SERVICE_UNAVAILABLE,
    StrategyAgentFailureCode.QUOTA: status.HTTP_429_TOO_MANY_REQUESTS,
    StrategyAgentFailureCode.TIMEOUT: status.HTTP_504_GATEWAY_TIMEOUT,
    StrategyAgentFailureCode.PROVIDER_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    StrategyAgentFailureCode.INVALID_PROVIDER_REQUEST: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.MALFORMED_PROVIDER_OUTPUT: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.INVALID_TOOL_REQUEST: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.TOOL_EXECUTION_LIMIT: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.TOOL_EXECUTION_FAILURE: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.PAYLOAD_LIMIT: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.REFERENCE_VALIDATION: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.CLAIM_VALIDATION: status.HTTP_502_BAD_GATEWAY,
    StrategyAgentFailureCode.PROVENANCE_VALIDATION: status.HTTP_502_BAD_GATEWAY,
}


@router.post("/strategy/answer", response_model=StrategyAgentAnswerResponse, tags=["Strategy Agent"])
async def answer_strategy_question(
    request: StrategyAgentAnswerRequest,
    service: StrategyAgent,
) -> StrategyAgentAnswerResponse:
    try:
        result = await service.answer(
            StrategyAgentRequest(
                organization=request.organization,
                question=request.question,
                time_horizon=request.time_horizon,
            )
        )
    except StrategyAgentError as error:
        raise HTTPException(
            status_code=_STRATEGY_FAILURE_STATUS[error.code],
            detail={"code": error.code.value, "message": _safe_strategy_message(error)},
        ) from error
    return StrategyAgentAnswerResponse.model_validate(result.model_dump())


_HIRING_FAILURE_STATUS = {
    HiringAgentFailureCode.DISABLED: status.HTTP_503_SERVICE_UNAVAILABLE,
    HiringAgentFailureCode.INVALID_REQUEST: status.HTTP_422_UNPROCESSABLE_ENTITY,
    HiringAgentFailureCode.AUTHENTICATION: status.HTTP_503_SERVICE_UNAVAILABLE,
    HiringAgentFailureCode.PROVIDER_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}


@router.post("/hiring/answer", response_model=HiringAgentAnswerResponse, tags=["Hiring Agent"])
async def answer_hiring_agent_request(
    request: HiringAgentAnswerRequest,
    service: HiringAgent,
) -> HiringAgentAnswerResponse:
    try:
        result = await service.answer(HiringAgentAppRequest(organization=request.organization))
    except HiringAgentError as error:
        raise HTTPException(
            status_code=_HIRING_FAILURE_STATUS[error.code],
            detail={"code": error.code.value, "message": _safe_hiring_message(error.code)},
        ) from error
    return HiringAgentAnswerResponse.model_validate(result.model_dump())


def _safe_hiring_message(code: HiringAgentFailureCode) -> str:
    if code == HiringAgentFailureCode.DISABLED:
        return "The Hiring Agent is currently disabled."
    if code == HiringAgentFailureCode.AUTHENTICATION:
        return "The Hiring Agent is not configured with valid credentials."
    return "The Hiring Agent is temporarily unavailable."


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


def _safe_strategy_message(error: StrategyAgentError) -> str:
    code = error.code
    if code == StrategyAgentFailureCode.ORGANIZATION_SCOPE_MISMATCH:
        return str(error)
    if code == StrategyAgentFailureCode.DISABLED:
        return "The Strategy Agent is currently disabled."
    if code == StrategyAgentFailureCode.QUOTA:
        return "The Strategy Agent is temporarily rate limited."
    if code == StrategyAgentFailureCode.TIMEOUT:
        return "The Strategy Agent request timed out."
    if code in {
        StrategyAgentFailureCode.INVALID_PROVIDER_REQUEST,
        StrategyAgentFailureCode.MALFORMED_PROVIDER_OUTPUT,
        StrategyAgentFailureCode.INVALID_TOOL_REQUEST,
        StrategyAgentFailureCode.TOOL_EXECUTION_LIMIT,
        StrategyAgentFailureCode.TOOL_EXECUTION_FAILURE,
        StrategyAgentFailureCode.PAYLOAD_LIMIT,
        StrategyAgentFailureCode.REFERENCE_VALIDATION,
        StrategyAgentFailureCode.CLAIM_VALIDATION,
        StrategyAgentFailureCode.PROVENANCE_VALIDATION,
    }:
        return "The Strategy Agent could not validate a governed answer."
    return "The Strategy Agent is temporarily unavailable."
