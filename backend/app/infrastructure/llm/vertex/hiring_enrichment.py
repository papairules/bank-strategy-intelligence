import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from backend.app.application.hiring.enrichment import (
    EnrichmentFailureCode,
    HiringEnrichmentError,
    HiringEnrichmentRequest,
    HiringProviderResponse,
    HiringProviderStructuredOutput,
    ProviderModelMetadata,
)


GROUNDING_INSTRUCTION = """
You extract structured hiring information from one supplied normalized job posting.

Grounding rules:
- Use only the supplied job and evidence text.
- Do not use outside knowledge about the organization.
- Do not manufacture skills, technologies, capabilities, business units, or themes.
- Return empty lists, null, false, or unknown whenever evidence is insufficient.
- Every extracted non-empty value must include a short verbatim supporting excerpt.
- Distinguish explicit evidence from interpretation and report limitations.
- Do not make investment claims, strategic certainty claims, consulting recommendations,
  or opportunity recommendations.
- Leadership may be true only when the supplied text sufficiently supports leadership scope.
- Use only values allowed by the response schema taxonomies.
""".strip()


class VertexGeminiHiringEnrichmentProvider:
    provider_name = "vertex_gemini"
    prompt_schema_version = "hiring-enrichment-v1"

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
            "response_json_schema": HiringProviderStructuredOutput.model_json_schema(),
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
            code = (
                EnrichmentFailureCode.AUTHENTICATION_CONFIGURATION
                if self._is_authentication_error(error)
                else EnrichmentFailureCode.PROVIDER_UNAVAILABLE
            )
            raise HiringEnrichmentError(
                code,
                "Vertex Gemini enrichment request failed.",
                metadata={"exception_type": type(error).__name__},
            ) from error

        try:
            parsed = getattr(response, "parsed", None)
            if parsed is None:
                text = getattr(response, "text", None)
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Vertex Gemini returned no structured response")
                parsed = json.loads(text)
            output = HiringProviderStructuredOutput.model_validate(parsed)
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT,
                "Vertex Gemini returned invalid structured output.",
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
