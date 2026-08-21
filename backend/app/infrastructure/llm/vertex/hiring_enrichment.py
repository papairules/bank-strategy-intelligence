import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from backend.app.application.hiring.enrichment import (
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


GROUNDING_INSTRUCTION = """
You extract structured hiring information from one supplied normalized job posting.

Grounding rules:
- Use only the supplied job and evidence text.
- Do not use outside knowledge about the organization.
- Do not manufacture skills, technologies, capabilities, business units, or themes.
- Return empty lists, null, false, or unknown whenever evidence is insufficient.
- Return at most 5 capabilities, 10 skills, 10 technologies, and 5 hiring themes.
- Skills and technologies must be concise names explicitly present in the supplied text.
- Use concise normalized labels and no prose commentary outside the schema.
- Do not make investment claims, strategic certainty claims, consulting recommendations,
  or opportunity recommendations.
- Leadership may be true only when the supplied text sufficiently supports leadership scope.
- Use only values allowed by the response schema taxonomies.
""".strip()


class VertexHiringEnrichmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_classifications: list[HiringCapability]
    skills: list[str]
    technologies: list[str]
    seniority_level: EnrichmentSeniority
    is_leadership: bool
    business_unit: str | None
    hiring_themes: list[HiringTheme]
    model_confidence: float

    @field_validator(
        "capability_classifications",
        "skills",
        "technologies",
        "hiring_themes",
    )
    @classmethod
    def require_unique_values(cls, values: list) -> list:
        if len(values) != len(set(values)):
            raise ValueError("provider output list values must be unique")
        return values

    @model_validator(mode="after")
    def validate_local_limits(self):
        limits = {
            "capability_classifications": 5,
            "skills": 10,
            "technologies": 10,
            "hiring_themes": 5,
        }
        for field, limit in limits.items():
            if len(getattr(self, field)) > limit:
                raise ValueError(f"{field} must contain at most {limit} values")
        if not 0 <= self.model_confidence <= 1:
            raise ValueError("model_confidence must be between 0 and 1")
        for field in ("skills", "technologies"):
            values = getattr(self, field)
            if any(not value.strip() or len(value) > 100 for value in values):
                raise ValueError(f"{field} values must be concise non-empty labels")
        if self.business_unit is not None and (
            not self.business_unit.strip() or len(self.business_unit) > 100
        ):
            raise ValueError("business_unit must be a concise non-empty label")
        return self

    def to_application_output(self) -> HiringProviderStructuredOutput:
        return HiringProviderStructuredOutput.model_validate(self.model_dump())


class VertexGeminiHiringEnrichmentProvider:
    provider_name = "vertex_gemini"
    prompt_schema_version = "hiring-enrichment-v3"

    def __init__(
        self,
        *,
        project: str | None,
        location: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any | None = None

    async def enrich(self, request: HiringEnrichmentRequest) -> HiringProviderResponse:
        client = self._client_instance()
        config = {
            "system_instruction": GROUNDING_INSTRUCTION,
            "temperature": self._temperature,
            "max_output_tokens": self._max_output_tokens,
            "response_mime_type": "application/json",
            "response_schema": VertexHiringEnrichmentOutput,
            "automatic_function_calling": {"disable": True},
        }
        contents = (
            "Enrich this normalized job posting using only the supplied fields.\n"
            f"{request.model_dump_json()}"
        )
        try:
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=contents,
                config=config,
            )
        except TimeoutError as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.TIMEOUT,
                "Vertex Gemini enrichment request timed out.",
            ) from error
        except HiringEnrichmentError:
            raise
        except Exception as error:
            code, metadata = self._classify_provider_error(error)
            raise HiringEnrichmentError(
                code,
                "Vertex Gemini enrichment request failed.",
                metadata=metadata,
            ) from error

        parsed = getattr(response, "parsed", None)
        text_present: bool | None = None
        transport_validation_attempted = False
        try:
            if isinstance(parsed, VertexHiringEnrichmentOutput):
                transport_output = parsed
            elif parsed is not None:
                transport_validation_attempted = True
                transport_output = VertexHiringEnrichmentOutput.model_validate(parsed)
            else:
                text = getattr(response, "text", None)
                text_present = isinstance(text, str) and bool(text.strip())
                if not text_present:
                    raise ValueError("Vertex Gemini returned no structured response")
                transport_validation_attempted = True
                transport_output = VertexHiringEnrichmentOutput.model_validate(
                    json.loads(text)
                )
            output = transport_output.to_application_output()
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
            diagnostics = self._response_diagnostics(
                response,
                parsed=parsed,
                text_present=text_present,
                transport_validation_attempted=transport_validation_attempted,
            )
            diagnostics.update(self._validation_summary(error))
            raise HiringEnrichmentError(
                EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT,
                "Vertex Gemini returned invalid structured output.",
                metadata=diagnostics,
            ) from error

        return HiringProviderResponse(
            output=output,
            metadata=ProviderModelMetadata(
                provider=self.provider_name,
                model=self._model,
                prompt_schema_version=self.prompt_schema_version,
                provider_request_id=self._optional_string(response, "response_id"),
                model_version=self._optional_string(response, "model_version"),
                usage_metadata=self._usage_metadata(response),
            ),
        )

    async def close(self) -> None:
        if self._client is None:
            return
        async_client = getattr(self._client, "aio", None)
        close = getattr(async_client, "aclose", None)
        if close is not None:
            await close()
        self._client = None

    def _client_instance(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._project or not self._project.strip():
            raise HiringEnrichmentError(
                EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION,
                "GCP project is required for Vertex Gemini enrichment.",
            )
        try:
            self._client = self._client_factory(
                vertexai=True,
                project=self._project,
                location=self._location,
            )
        except HiringEnrichmentError:
            raise
        except Exception as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION,
                "Vertex Gemini client could not be initialized with runtime credentials.",
                metadata={"exception_type": type(error).__name__},
            ) from error
        return self._client

    @staticmethod
    def _default_client_factory(**kwargs: Any) -> Any:
        try:
            from google import genai
        except ImportError as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION,
                "google-genai is not installed.",
            ) from error
        return genai.Client(**kwargs)

    @staticmethod
    def _is_authentication_error(error: Exception) -> bool:
        name = type(error).__name__.casefold()
        return any(
            value in name
            for value in (
                "credential",
                "authentication",
                "unauthenticated",
                "permissiondenied",
                "forbidden",
            )
        )

    @classmethod
    def _classify_provider_error(
        cls,
        error: Exception,
    ) -> tuple[EnrichmentFailureCode, dict[str, Any]]:
        code = getattr(error, "code", None)
        status = getattr(error, "status", None)
        message = cls._sanitize_error_message(getattr(error, "message", None))
        reason = cls._safe_error_reason(getattr(error, "details", None))
        metadata: dict[str, Any] = {"exception_type": type(error).__name__}
        if isinstance(code, int):
            metadata["http_status_code"] = code
        if isinstance(status, str) and status:
            metadata["error_status"] = status[:100]
        if message:
            metadata["error_message"] = message
        if reason:
            metadata["error_reason"] = reason

        searchable = " ".join(
            value.casefold()
            for value in (status, message, reason)
            if isinstance(value, str)
        )
        if code == 401 or cls._is_authentication_error(error):
            failure = EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION
        elif code == 403:
            failure = (
                EnrichmentFailureCode.BILLING_QUOTA
                if any(value in searchable for value in ("billing", "quota"))
                else EnrichmentFailureCode.PERMISSION_DENIED
            )
        elif code == 429:
            failure = EnrichmentFailureCode.BILLING_QUOTA
        elif code in {400, 404} and any(
            value in searchable
            for value in ("model", "location", "publisher", "not found")
        ):
            failure = EnrichmentFailureCode.MODEL_LOCATION
        elif code == 400:
            failure = EnrichmentFailureCode.INVALID_REQUEST
        else:
            failure = EnrichmentFailureCode.PROVIDER_UNAVAILABLE
        return failure, metadata

    @staticmethod
    def _sanitize_error_message(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        sanitized = " ".join(value.split())
        sanitized = re.sub(
            r"(?i)\bbearer\s+\S+",
            "Bearer [REDACTED]",
            sanitized,
        )
        sanitized = re.sub(
            r"(?i)\b(access[_ -]?token|api[_ -]?key)\s*[:=]\s*\S+",
            r"\1 [REDACTED]",
            sanitized,
        )
        sanitized = re.sub(
            r"(?i)\bauthorization\s*:\s*\S+(?:\s+\S+)?",
            "Authorization [REDACTED]",
            sanitized,
        )
        return sanitized[:300]

    @classmethod
    def _safe_error_reason(cls, details: Any) -> str | None:
        if isinstance(details, dict):
            reason = details.get("reason")
            if isinstance(reason, str) and reason:
                return cls._sanitize_error_message(reason)[:100]
            for key in ("error", "details"):
                nested = cls._safe_error_reason(details.get(key))
                if nested:
                    return nested
        elif isinstance(details, list):
            for item in details:
                nested = cls._safe_error_reason(item)
                if nested:
                    return nested
        return None

    @staticmethod
    def _optional_string(value: Any, attribute: str) -> str | None:
        item = getattr(value, attribute, None)
        return item if isinstance(item, str) and item else None

    @staticmethod
    def _usage_metadata(response: Any) -> dict[str, Any]:
        value = getattr(response, "usage_metadata", None)
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        model_dump = getattr(value, "model_dump", None)
        if model_dump is not None:
            return model_dump(mode="json")
        return {}

    @staticmethod
    def _validation_summary(error: Exception) -> dict[str, Any]:
        if isinstance(error, ValidationError):
            errors = error.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )
            return {
                "error_type": "schema_validation",
                "error_count": len(errors),
                "validation_errors": [
                    {
                        "location": ".".join(str(item) for item in value["loc"]),
                        "type": value["type"],
                    }
                    for value in errors
                ],
            }
        if isinstance(error, json.JSONDecodeError):
            return {"error_type": "invalid_json"}
        return {"error_type": type(error).__name__}

    @classmethod
    def _response_diagnostics(
        cls,
        response: Any,
        *,
        parsed: Any,
        text_present: bool | None,
        transport_validation_attempted: bool,
    ) -> dict[str, Any]:
        return {
            "parsed_present": parsed is not None,
            "parsed_type": type(parsed).__name__ if parsed is not None else None,
            "text_present": text_present,
            "finish_reason": cls._finish_reason(response),
            "transport_validation_attempted": transport_validation_attempted,
        }

    @staticmethod
    def _finish_reason(response: Any) -> str | None:
        candidates = getattr(response, "candidates", None)
        if not candidates:
            return None
        value = getattr(candidates[0], "finish_reason", None)
        if value is None:
            return None
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, str):
            return enum_value
        return str(value)
