from collections.abc import Callable
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.app.domain.hiring import JobPosting, SeniorityLevel
from backend.app.domain.intelligence import Evidence


class HiringCapability(StrEnum):
    AI_ML = "Artificial Intelligence / Machine Learning"
    DATA_ANALYTICS = "Data & Analytics"
    SOFTWARE_ENGINEERING = "Software Engineering"
    CLOUD_INFRASTRUCTURE = "Cloud & Infrastructure"
    CYBERSECURITY = "Cybersecurity"
    RISK_COMPLIANCE = "Risk & Compliance"
    DIGITAL_BANKING = "Digital Banking"
    PAYMENTS = "Payments"
    OPERATIONS = "Operations"
    FINANCE = "Finance"
    CUSTOMER_EXPERIENCE = "Customer Experience"
    PRODUCT_MANAGEMENT = "Product Management"
    OTHER = "Other"


class EnrichmentSeniority(StrEnum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    EXECUTIVE = "executive"
    UNKNOWN = "unknown"


class HiringTheme(StrEnum):
    AI_ADOPTION = "AI adoption"
    CLOUD_MODERNIZATION = "cloud modernization"
    DATA_MODERNIZATION = "data modernization"
    RISK_MODERNIZATION = "risk modernization"
    CYBERSECURITY = "cybersecurity"
    DIGITAL_TRANSFORMATION = "digital transformation"
    PLATFORM_ENGINEERING = "platform engineering"


class EnrichmentField(StrEnum):
    CAPABILITY_CLASSIFICATIONS = "capability_classifications"
    SKILLS = "skills"
    TECHNOLOGIES = "technologies"
    SENIORITY_LEVEL = "seniority_level"
    IS_LEADERSHIP = "is_leadership"
    BUSINESS_UNIT = "business_unit"
    HIRING_THEMES = "hiring_themes"


class ExistingNormalizedMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_unit: str | None = None
    capability_classifications: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    seniority_level: SeniorityLevel | None = None
    is_leadership: bool = False


class HiringEnrichmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    organization: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str | None = None
    evidence_excerpt: str | None = None
    location: str = Field(min_length=1)
    existing_normalized_metadata: ExistingNormalizedMetadata
    evidence_id: UUID

    @model_validator(mode="after")
    def require_evidence_text(self) -> Self:
        if not any(
            value is not None and value.strip()
            for value in (self.description, self.evidence_excerpt)
        ):
            raise ValueError("description or evidence_excerpt must contain text")
        return self


class ProviderFieldSupport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: EnrichmentField
    value: str = Field(min_length=1)
    excerpt: str = Field(min_length=1, max_length=500)


class EnrichmentFieldSupport(ProviderFieldSupport):
    evidence_id: UUID


class HiringProviderStructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_classifications: list[HiringCapability] = Field(
        default_factory=list,
        max_length=5,
    )
    skills: list[str] = Field(default_factory=list, max_length=10)
    technologies: list[str] = Field(default_factory=list, max_length=10)
    seniority_level: EnrichmentSeniority = EnrichmentSeniority.UNKNOWN
    is_leadership: bool = False
    business_unit: str | None = Field(default=None, max_length=100)
    hiring_themes: list[HiringTheme] = Field(default_factory=list, max_length=5)
    model_confidence: float = Field(ge=0, le=1)

    @field_validator(
        "capability_classifications",
        "skills",
        "technologies",
        "hiring_themes",
    )
    @classmethod
    def require_unique_list_values(cls, values: list) -> list:
        if len(values) != len(set(values)):
            raise ValueError("list values must be unique")
        return values

    @field_validator("skills", "technologies")
    @classmethod
    def reject_blank_strings(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("list values must not be blank")
        return values

class ProviderModelMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_schema_version: str = Field(min_length=1)
    provider_request_id: str | None = None
    model_version: str | None = None
    usage_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class HiringProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output: HiringProviderStructuredOutput
    metadata: ProviderModelMetadata


class EnrichmentModelMetadata(ProviderModelMetadata):
    enrichment_timestamp: datetime
    model_confidence: float = Field(ge=0, le=1)

    @field_validator("enrichment_timestamp")
    @classmethod
    def require_timezone_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("enrichment_timestamp must be timezone-aware")
        return value


class HiringEnrichmentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    evidence_id: UUID
    capability_classifications: list[HiringCapability] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    seniority_level: EnrichmentSeniority
    is_leadership: bool
    business_unit: str | None = None
    hiring_themes: list[HiringTheme] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    field_confidences: dict[EnrichmentField, float] = Field(default_factory=dict)
    field_support: list[EnrichmentFieldSupport] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    model_metadata: EnrichmentModelMetadata


class EnrichmentFailureCode(StrEnum):
    DISABLED = "enrichment_disabled"
    EMPTY_EVIDENCE = "empty_evidence"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    AUTHENTICATION_CONFIGURATION = "authentication_configuration"
    PERMISSION_DENIED = "permission_denied"
    BILLING_QUOTA = "billing_quota"
    MODEL_LOCATION = "model_location"
    INVALID_REQUEST = "invalid_request"
    TIMEOUT = "timeout"
    MALFORMED_STRUCTURED_OUTPUT = "malformed_structured_output"
    VALIDATION_FAILURE = "validation_failure"


class HiringEnrichmentError(Exception):
    def __init__(
        self,
        code: EnrichmentFailureCode,
        message: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class HiringEnrichmentProvider(Protocol):
    async def enrich(self, request: HiringEnrichmentRequest) -> HiringProviderResponse: ...


class HiringEnrichmentService:
    def __init__(
        self,
        provider: HiringEnrichmentProvider,
        *,
        enabled: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._provider = provider
        self._enabled = enabled
        self._clock = clock

    async def enrich(
        self,
        posting: JobPosting,
        evidence: Evidence,
    ) -> HiringEnrichmentResult:
        if not self._enabled:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.DISABLED,
                "Hiring enrichment is disabled.",
            )
        if posting.evidence_id != evidence.evidence_id:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.VALIDATION_FAILURE,
                "JobPosting and Evidence IDs do not match.",
            )
        try:
            request = self._request(posting, evidence)
        except ValidationError as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.EMPTY_EVIDENCE,
                "Normalized job and evidence contain no usable enrichment text.",
            ) from error

        provider_value = await self._provider.enrich(request)
        try:
            provider_response = HiringProviderResponse.model_validate(provider_value)
            self._validate_explicit_grounding(request, provider_response.output)
        except ValidationError as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.MALFORMED_STRUCTURED_OUTPUT,
                "Provider returned malformed structured output.",
            ) from error
        except ValueError as error:
            raise HiringEnrichmentError(
                EnrichmentFailureCode.VALIDATION_FAILURE,
                str(error),
            ) from error

        output = provider_response.output
        supports = self._deterministic_support(request, output, evidence.evidence_id)
        confidence, field_confidences = self._adjust_confidence(
            request,
            output,
            supports,
        )
        return HiringEnrichmentResult(
            job_id=posting.job_id,
            evidence_id=evidence.evidence_id,
            capability_classifications=output.capability_classifications,
            skills=output.skills,
            technologies=output.technologies,
            seniority_level=output.seniority_level,
            is_leadership=output.is_leadership,
            business_unit=output.business_unit,
            hiring_themes=output.hiring_themes,
            confidence=confidence,
            field_confidences=field_confidences,
            field_support=supports,
            limitations=self._limitations(output),
            model_metadata=EnrichmentModelMetadata(
                **provider_response.metadata.model_dump(),
                enrichment_timestamp=self._clock(),
                model_confidence=output.model_confidence,
            ),
        )

    @staticmethod
    def _request(posting: JobPosting, evidence: Evidence) -> HiringEnrichmentRequest:
        return HiringEnrichmentRequest(
            job_id=posting.job_id,
            organization=posting.organization,
            title=posting.title,
            description=posting.description,
            evidence_excerpt=evidence.source_excerpt,
            location=posting.location,
            existing_normalized_metadata=ExistingNormalizedMetadata(
                business_unit=posting.business_unit,
                capability_classifications=posting.capability_classifications,
                skills=posting.skills,
                technologies=posting.technologies,
                seniority_level=posting.seniority_level,
                is_leadership=posting.is_leadership,
            ),
            evidence_id=evidence.evidence_id,
        )

    @classmethod
    def _validate_explicit_grounding(
        cls,
        request: HiringEnrichmentRequest,
        output: HiringProviderStructuredOutput,
    ) -> None:
        supplied_text = cls._supplied_text(request).casefold()
        for field, values in (
            (EnrichmentField.SKILLS, output.skills),
            (EnrichmentField.TECHNOLOGIES, output.technologies),
        ):
            for value in values:
                if value.strip().casefold() not in supplied_text:
                    raise ValueError(
                        f"{field.value} value is not explicitly present in supplied evidence"
                    )

    @staticmethod
    def _extracted_values(
        output: HiringProviderStructuredOutput,
    ) -> set[tuple[EnrichmentField, str]]:
        values: set[tuple[EnrichmentField, str]] = set()
        values.update(
            (EnrichmentField.CAPABILITY_CLASSIFICATIONS, item.value.casefold())
            for item in output.capability_classifications
        )
        values.update((EnrichmentField.SKILLS, item.casefold()) for item in output.skills)
        values.update(
            (EnrichmentField.TECHNOLOGIES, item.casefold())
            for item in output.technologies
        )
        if output.seniority_level is not EnrichmentSeniority.UNKNOWN:
            values.add(
                (EnrichmentField.SENIORITY_LEVEL, output.seniority_level.value.casefold())
            )
        if output.is_leadership:
            values.add((EnrichmentField.IS_LEADERSHIP, "true"))
        if output.business_unit:
            values.add((EnrichmentField.BUSINESS_UNIT, output.business_unit.casefold()))
        values.update(
            (EnrichmentField.HIRING_THEMES, item.value.casefold())
            for item in output.hiring_themes
        )
        return values

    @classmethod
    def _adjust_confidence(
        cls,
        request: HiringEnrichmentRequest,
        output: HiringProviderStructuredOutput,
        supports: list[EnrichmentFieldSupport],
    ) -> tuple[float, dict[EnrichmentField, float]]:
        evidence_availability = (
            1.0
            if request.description and request.evidence_excerpt
            else 0.75
        )
        extracted = cls._extracted_values(output)
        supported = {
            (support.field, support.value.strip().casefold())
            for support in supports
        }
        explicit_values = {
            value for value in extracted if value[0] in {
                EnrichmentField.SKILLS,
                EnrichmentField.TECHNOLOGIES,
            }
        }
        support_coverage = (
            len(explicit_values & supported) / len(explicit_values)
            if explicit_values
            else 1.0
        )
        populated_categories = len({field for field, _ in extracted})
        completeness = populated_categories / len(EnrichmentField)
        confidence = cls._bounded(
            round((evidence_availability + support_coverage + completeness) / 3, 4)
        )
        field_confidences = {}
        for field in {field for field, _ in extracted}:
            field_confidences[field] = (
                1.0 if any(item[0] is field for item in supported) else 0.65
            )
        return confidence, field_confidences

    @classmethod
    def _deterministic_support(
        cls,
        request: HiringEnrichmentRequest,
        output: HiringProviderStructuredOutput,
        evidence_id: UUID,
    ) -> list[EnrichmentFieldSupport]:
        supplied_text = cls._supplied_text(request)
        values: list[tuple[EnrichmentField, str]] = []
        values.extend((EnrichmentField.SKILLS, item) for item in output.skills)
        values.extend((EnrichmentField.TECHNOLOGIES, item) for item in output.technologies)
        if output.business_unit:
            values.append((EnrichmentField.BUSINESS_UNIT, output.business_unit))
        if output.seniority_level is not EnrichmentSeniority.UNKNOWN:
            values.append((EnrichmentField.SENIORITY_LEVEL, output.seniority_level.value))
        supports: list[EnrichmentFieldSupport] = []
        folded_text = supplied_text.casefold()
        for field, value in values:
            start = folded_text.find(value.casefold())
            if start >= 0:
                supports.append(
                    EnrichmentFieldSupport(
                        field=field,
                        value=value,
                        excerpt=supplied_text[start : start + len(value)],
                        evidence_id=evidence_id,
                    )
                )
        return supports

    @staticmethod
    def _limitations(output: HiringProviderStructuredOutput) -> list[str]:
        limitations = ["Enrichment uses only the supplied job posting evidence."]
        if output.capability_classifications or output.hiring_themes:
            limitations.append(
                "Capability and theme labels are semantic classifications, not strategic claims."
            )
        return limitations

    @staticmethod
    def _supplied_text(request: HiringEnrichmentRequest) -> str:
        return "\n".join(
            value
            for value in (
                request.title,
                request.description,
                request.evidence_excerpt,
            )
            if value
        )

    @staticmethod
    def _bounded(value: float) -> float:
        return max(0.0, min(1.0, value))
