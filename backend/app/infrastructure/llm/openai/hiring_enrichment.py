import asyncio
from collections.abc import Callable
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    ContentFilterFinishReasonError,
    InternalServerError,
    LengthFinishReasonError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.application.hiring import (
    EnrichmentFailureCode,
    EnrichmentSeniority,
    HiringCapability,
    HiringEnrichmentError,
    HiringEnrichmentRequest,
    HiringProviderResponse,
    HiringProviderStructuredOutput,
    HiringTheme,
    ProviderModelMetadata,
)


GROUNDING_INSTRUCTION = """Extract structured hiring information from one supplied normalized job.
Use only the supplied title, description, evidence excerpt, location, and existing metadata.
Do not use web search, outside knowledge, URLs, tools, or external job sources.
Do not invent skills, technologies, capabilities, business units, themes, or leadership scope.
Skills and technologies must be explicitly present in supplied text. Return empty or unknown values
when evidence is insufficient. Capability and theme values should use the canonical labels described
by the response schema. Seniority may be a canonical label or source wording; Vice President/VP maps
to director for this canonical taxonomy and must not map to executive solely because it says VP.
Set is_leadership only when the supplied role text explicitly supports director/executive leadership.
Return structured data only."""


class OpenAIHiringEnrichmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_classifications: list[str] = Field(default_factory=list, max_length=5)
    skills: list[str] = Field(default_factory=list, max_length=10)
    technologies: list[str] = Field(default_factory=list, max_length=10)
    seniority_level: str = "unknown"
    is_leadership: bool = False
    business_unit: str | None = Field(default=None, max_length=100)
    hiring_themes: list[str] = Field(default_factory=list, max_length=5)
    model_confidence: float = Field(ge=0, le=1)

    @field_validator("skills", "technologies")
    @classmethod
    def clean_explicit_labels(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 100 for value in cleaned):
            raise ValueError("skills and technologies must be concise")
        return cleaned

    def to_application_output(self) -> HiringProviderStructuredOutput:
        seniority = normalize_seniority(self.seniority_level)
        leadership = self.is_leadership and seniority in {
            EnrichmentSeniority.DIRECTOR,
            EnrichmentSeniority.EXECUTIVE,
        }
        return HiringProviderStructuredOutput(
            capability_classifications=normalize_capabilities(
                self.capability_classifications
            ),
            skills=self.skills,
            technologies=self.technologies,
            seniority_level=seniority,
            is_leadership=leadership,
            business_unit=self.business_unit,
            hiring_themes=normalize_themes(self.hiring_themes),
            model_confidence=self.model_confidence,
        )


def _key(value: str) -> str:
    return " ".join(
        value.casefold().replace("&", " and ").replace("/", " ").split()
    )


_CAPABILITY_ALIASES = {
    _key(item.value): item for item in HiringCapability
}
_CAPABILITY_ALIASES.update(
    {
        "ai": HiringCapability.AI_ML,
        "ai ml": HiringCapability.AI_ML,
        "data and ai": HiringCapability.AI_ML,
        "machine learning": HiringCapability.AI_ML,
        "data analytics": HiringCapability.DATA_ANALYTICS,
        "data and analytics": HiringCapability.DATA_ANALYTICS,
        "cloud and platform engineering": HiringCapability.CLOUD_INFRASTRUCTURE,
        "cloud infrastructure": HiringCapability.CLOUD_INFRASTRUCTURE,
        "risk and compliance": HiringCapability.RISK_COMPLIANCE,
        "product and digital": HiringCapability.DIGITAL_BANKING,
        "operations and automation": HiringCapability.OPERATIONS,
    }
)


def normalize_capabilities(values: list[str]) -> list[HiringCapability]:
    normalized: list[HiringCapability] = []
    for value in values:
        capability = _CAPABILITY_ALIASES.get(_key(value))
        if capability is not None and capability not in normalized:
            normalized.append(capability)
    return normalized


_SENIORITY_ALIASES = {
    "entry": EnrichmentSeniority.ENTRY,
    "junior": EnrichmentSeniority.ENTRY,
    "mid": EnrichmentSeniority.MID,
    "mid level": EnrichmentSeniority.MID,
    "senior": EnrichmentSeniority.SENIOR,
    "staff": EnrichmentSeniority.SENIOR,
    "lead": EnrichmentSeniority.LEAD,
    "principal": EnrichmentSeniority.LEAD,
    "manager": EnrichmentSeniority.MANAGER,
    "director": EnrichmentSeniority.DIRECTOR,
    "vp": EnrichmentSeniority.DIRECTOR,
    "vice president": EnrichmentSeniority.DIRECTOR,
    "executive": EnrichmentSeniority.EXECUTIVE,
    "unknown": EnrichmentSeniority.UNKNOWN,
}


def normalize_seniority(value: str) -> EnrichmentSeniority:
    return _SENIORITY_ALIASES.get(_key(value), EnrichmentSeniority.UNKNOWN)


_THEME_ALIASES = {_key(item.value): item for item in HiringTheme}


def normalize_themes(values: list[str]) -> list[HiringTheme]:
    normalized: list[HiringTheme] = []
    for value in values:
        theme = _THEME_ALIASES.get(_key(value))
        if theme is not None and theme not in normalized:
            normalized.append(theme)
    return normalized


class OpenAIHiringEnrichmentProvider:
    provider_name = "openai"
    prompt_schema_version = "openai-hiring-enrichment-v1"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client_factory = client_factory or OpenAI
        self._client: Any | None = None

    async def enrich(self, request: HiringEnrichmentRequest) -> HiringProviderResponse:
        try:
            response = await asyncio.to_thread(
                self._client_instance().responses.parse,
                model=self._model,
                instructions=GROUNDING_INSTRUCTION,
                input=request.model_dump_json(),
                text_format=OpenAIHiringEnrichmentOutput,
            )
        except APITimeoutError as error:
            raise self._error(EnrichmentFailureCode.TIMEOUT, "timeout", error) from error
        except AuthenticationError as error:
            raise self._error(
                EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION,
                "authentication",
                error,
            ) from error
        except PermissionDeniedError as error:
            raise self._error(
                EnrichmentFailureCode.PERMISSION_DENIED, "permission_denied", error
            ) from error
        except RateLimitError as error:
            raise self._error(
                EnrichmentFailureCode.BILLING_QUOTA, "rate_limit", error
            ) from error
        except BadRequestError as error:
            raise self._error(
                EnrichmentFailureCode.INVALID_REQUEST, "bad_request", error
            ) from error
        except UnprocessableEntityError as error:
            raise self._error(
                EnrichmentFailureCode.INVALID_REQUEST, "unprocessable_entity", error
            ) from error
        except NotFoundError as error:
            raise self._error(
                EnrichmentFailureCode.INVALID_REQUEST, "not_found", error
            ) from error
        except ConflictError as error:
            raise self._error(
                EnrichmentFailureCode.INVALID_REQUEST, "conflict", error
            ) from error
        except InternalServerError as error:
            raise self._error(
                EnrichmentFailureCode.PROVIDER_UNAVAILABLE,
                "internal_server_error",
                error,
            ) from error
        except APIConnectionError as error:
            raise self._error(
                EnrichmentFailureCode.PROVIDER_UNAVAILABLE,
                "connection_error",
                error,
            ) from error
        except APIStatusError as error:
            code = (
                EnrichmentFailureCode.PROVIDER_UNAVAILABLE
                if error.status_code >= 500
                else EnrichmentFailureCode.INVALID_REQUEST
            )
            raise self._error(code, "api_status_error", error) from error
        except (LengthFinishReasonError, ContentFilterFinishReasonError) as error:
            raise self._error(
                EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT,
                "structured_output_parsing",
                error,
            ) from error
        except HiringEnrichmentError:
            raise
        except Exception as error:
            raise self._error(
                EnrichmentFailureCode.PROVIDER_UNAVAILABLE,
                "unexpected_sdk_error",
                error,
            ) from error

        parsed = getattr(response, "output_parsed", None)
        try:
            transport = OpenAIHiringEnrichmentOutput.model_validate(parsed)
            output = transport.to_application_output()
        except Exception as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT,
                "OpenAI returned invalid structured hiring enrichment.",
                metadata={
                    "error_category": "structured_output_validation",
                    "exception_type": type(error).__name__,
                    "status_code": None,
                    "request_id": _optional_text(response, "id"),
                    "sanitized_message": "OpenAI structured output was invalid.",
                    "parsed_type": type(parsed).__name__,
                },
            ) from error
        return HiringProviderResponse(
            output=output,
            metadata=ProviderModelMetadata(
                provider=self.provider_name,
                model=self._model,
                prompt_schema_version=self.prompt_schema_version,
                provider_request_id=_optional_text(response, "id"),
                model_version=_optional_text(response, "model"),
                usage_metadata=_usage_metadata(response),
            ),
        )

    def _client_instance(self) -> Any:
        if self._client is None:
            if not self._api_key.strip():
                raise HiringEnrichmentError(
                    EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION,
                    "OpenAI API credentials are required for hiring enrichment.",
                )
            self._client = self._client_factory(api_key=self._api_key)
        return self._client

    @staticmethod
    def _error(
        code: EnrichmentFailureCode,
        category: str,
        error: Exception,
    ) -> HiringEnrichmentError:
        status_code = getattr(error, "status_code", None)
        request_id = getattr(error, "request_id", None)
        if request_id is None:
            response = getattr(error, "response", None)
            request_id = (
                response.headers.get("x-request-id")
                if response is not None and hasattr(response, "headers")
                else None
            )
        message = (
            f"OpenAI returned HTTP {status_code}."
            if isinstance(status_code, int)
            else f"OpenAI {category.replace('_', ' ')}."
        )
        return HiringEnrichmentError(
            code,
            "OpenAI hiring enrichment request failed.",
            metadata={
                "error_category": category,
                "exception_type": type(error).__name__,
                "status_code": status_code,
                "request_id": request_id if isinstance(request_id, str) else None,
                "sanitized_message": message,
            },
        )


def _optional_text(value: Any, name: str) -> str | None:
    candidate = getattr(value, name, None)
    return candidate if isinstance(candidate, str) and candidate.strip() else None


def _usage_metadata(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    if isinstance(usage, dict):
        return usage
    return {}
