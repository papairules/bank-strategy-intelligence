from dataclasses import dataclass, field
from uuid import UUID

from pydantic import ValidationError

from backend.app.application.agents import (
    AgentEvidenceDetailResult,
    AgentToolRegistry,
    EvidenceAgentTools,
    EvidenceIdInput,
    EvidenceSearchInput,
    OrganizationInput,
)
from backend.app.application.agents.context import compact_agent_context
from backend.app.application.agents.models import EvidenceTrace
from backend.app.application.evidence import UnifiedEvidencePage, UnifiedEvidenceRecord

from .models import (
    EvidenceAgentAnswer,
    EvidenceAgentCitation,
    EvidenceAgentError,
    EvidenceAgentFailureCode,
    EvidenceAgentProviderRequest,
    EvidenceAgentProviderResponse,
    EvidenceAgentProviderStage,
    EvidenceAgentRequest,
    EvidenceAgentResult,
    EvidenceAgentStatus,
    EvidenceAgentToolCall,
    EvidenceAgentToolResult,
    EvidenceAgentToolSpec,
    EvidenceRelationshipType,
)
from .prompts import EVIDENCE_AGENT_SYSTEM_POLICY
from .provider import EvidenceAgentProvider
from .validation import excerpt_is_grounded


ALLOWED_TOOLS = (
    "evidence.get_summary",
    "evidence.search",
    "evidence.get",
    "evidence.trace",
)


@dataclass
class _EvidenceCatalogEntry:
    job_id: UUID
    organization: str
    source_type: str | None = None
    excerpts: set[str] = field(default_factory=set)
    relationships: set[EvidenceRelationshipType] = field(
        default_factory=lambda: {EvidenceRelationshipType.SOURCE_EVIDENCE}
    )


class EvidenceAgentService:
    agent_version = "evidence-agent-v1"

    def __init__(
        self,
        tools: EvidenceAgentTools,
        provider: EvidenceAgentProvider,
        *,
        enabled: bool = False,
        max_tool_calls: int = 3,
        max_evidence_records: int = 10,
        registry: AgentToolRegistry | None = None,
    ) -> None:
        if max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
        if not 1 <= max_evidence_records <= 20:
            raise ValueError("max_evidence_records must be between 1 and 20")
        self._tools = tools
        self._provider = provider
        self._enabled = enabled
        self._max_tool_calls = max_tool_calls
        self._max_evidence_records = max_evidence_records
        self._registry = registry or AgentToolRegistry()

    async def answer(self, request: EvidenceAgentRequest) -> EvidenceAgentResult:
        if not self._enabled:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.DISABLED,
                "Evidence Agent is disabled.",
            )
        maximum_evidence = min(
            request.maximum_evidence_records,
            self._max_evidence_records,
        )
        specs = self._tool_specs()
        plan = await self._provider_response(
            EvidenceAgentProviderRequest(
                stage=EvidenceAgentProviderStage.PLAN,
                system_policy=EVIDENCE_AGENT_SYSTEM_POLICY,
                request=request,
                allowed_tools=specs,
            )
        )
        if plan.answer is not None:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT,
                "Evidence provider returned an answer during tool planning.",
            )
        if len(plan.tool_calls) > self._max_tool_calls:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.TOOL_EXECUTION_LIMIT,
                "Evidence provider requested too many tool executions.",
                metadata={"requested": len(plan.tool_calls), "maximum": self._max_tool_calls},
            )

        catalog: dict[UUID, _EvidenceCatalogEntry] = {}
        tool_results = [
            self._execute_tool(call, request, maximum_evidence, catalog)
            for call in plan.tool_calls
        ]
        final = await self._provider_response(
            EvidenceAgentProviderRequest(
                stage=EvidenceAgentProviderStage.ANSWER,
                system_policy=EVIDENCE_AGENT_SYSTEM_POLICY,
                request=request,
                allowed_tools=specs,
                tool_results=tool_results,
            )
        )
        if final.tool_calls or final.answer is None:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT,
                "Evidence provider did not return one final structured answer.",
            )
        self._validate_answer(final.answer, request, catalog)
        reliability = self._reliability(final.answer, catalog, maximum_evidence)
        limitations = self._result_limitations(final.answer, tool_results)
        return EvidenceAgentResult(
            status=final.answer.status,
            organization=request.organization,
            question=request.question,
            answer=final.answer.answer,
            citations=final.answer.citations,
            evidence_records_considered=len(catalog),
            tool_calls_used=len(tool_results),
            reliability=reliability,
            limitations=limitations,
            provider=final.provider,
            model=final.model,
            agent_version=self.agent_version,
        )

    @classmethod
    def _result_limitations(
        cls,
        answer: EvidenceAgentAnswer,
        tool_results: list[EvidenceAgentToolResult],
    ) -> list[str]:
        values = list(answer.limitations)
        if answer.status == EvidenceAgentStatus.INSUFFICIENT_EVIDENCE:
            values.extend(
                (
                    "Available evidence is derived from hiring and career-site records.",
                    "Hiring evidence does not establish enterprise-wide technology adoption or production deployment.",
                    "Available evidence may not represent organization-wide strategy.",
                )
            )
            if cls._has_limited_observation_period(tool_results):
                values.append("The current observation period is limited.")
        deduplicated: dict[str, str] = {}
        for value in values:
            cleaned = value.strip()
            if cleaned:
                deduplicated.setdefault(cleaned.casefold(), cleaned)
        return list(deduplicated.values())

    @staticmethod
    def _has_limited_observation_period(
        tool_results: list[EvidenceAgentToolResult],
    ) -> bool:
        from datetime import date

        periods: list[tuple[date, date]] = []

        def visit(value: object) -> None:
            if isinstance(value, dict):
                start = value.get("observation_start")
                end = value.get("observation_end")
                if isinstance(start, str) and isinstance(end, str):
                    try:
                        periods.append((date.fromisoformat(start), date.fromisoformat(end)))
                    except ValueError:
                        pass
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        for result in tool_results:
            visit(result.result)
        return any((end - start).days < 28 for start, end in periods)

    async def _provider_response(
        self,
        request: EvidenceAgentProviderRequest,
    ) -> EvidenceAgentProviderResponse:
        try:
            response = await self._provider.respond(request)
            return EvidenceAgentProviderResponse.model_validate(response)
        except EvidenceAgentError:
            raise
        except TimeoutError as error:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.TIMEOUT,
                "Evidence provider request timed out.",
            ) from error
        except ValidationError as error:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.MALFORMED_PROVIDER_OUTPUT,
                "Evidence provider returned malformed structured output.",
                metadata={"validation_error_count": len(error.errors())},
            ) from error
        except Exception as error:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.PROVIDER_UNAVAILABLE,
                "Evidence provider is unavailable.",
                metadata={"exception_type": type(error).__name__},
            ) from error

    def _execute_tool(
        self,
        call: EvidenceAgentToolCall,
        request: EvidenceAgentRequest,
        maximum_evidence: int,
        catalog: dict[UUID, _EvidenceCatalogEntry],
    ) -> EvidenceAgentToolResult:
        if call.name not in ALLOWED_TOOLS:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.INVALID_TOOL_REQUEST,
                "Evidence provider requested an unapproved tool.",
                metadata={"tool": call.name},
            )
        try:
            if call.name == "evidence.get_summary":
                result = self._tools.get_summary(
                    OrganizationInput(organization=request.organization)
                )
            elif call.name == "evidence.search":
                result = self._search(call, request, maximum_evidence)
                for record in result.items:
                    self._catalog_record(record, catalog)
            else:
                evidence_id = self._validated_evidence_id(call, request)
                if call.name == "evidence.get":
                    result = self._tools.get(
                        EvidenceIdInput(
                            organization=request.organization,
                            evidence_id=evidence_id,
                        )
                    )
                    result = self._scope_detail(result, request.organization)
                    if result.found and result.detail is not None:
                        projected = compact_agent_context(
                            result.detail.model_dump(mode="json"),
                            question=request.question,
                        )
                        result = AgentEvidenceDetailResult.model_validate(
                            {"found": True, "detail": projected}
                        )
                        self._catalog_record(result.detail, catalog)
                else:
                    result = self._tools.trace(
                        EvidenceIdInput(
                            organization=request.organization,
                            evidence_id=evidence_id,
                        )
                    )
                    result = self._scope_trace(result, request.organization)
                    if result.found and result.job_id is not None:
                        self._catalog_trace(result, catalog)
        except EvidenceAgentError:
            raise
        except (ValidationError, ValueError, TypeError) as error:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.INVALID_TOOL_REQUEST,
                "Evidence provider supplied invalid tool arguments.",
                metadata={"tool": call.name},
            ) from error
        payload = compact_agent_context(
            result.model_dump(mode="json"),
            question=request.question,
        )
        return EvidenceAgentToolResult(
            call_id=call.call_id,
            name=call.name,
            result=payload,
        )

    def _search(
        self,
        call: EvidenceAgentToolCall,
        request: EvidenceAgentRequest,
        maximum_evidence: int,
    ) -> UnifiedEvidencePage:
        arguments = dict(call.arguments)
        constraints = request.search_constraints
        if constraints is not None:
            arguments.update(constraints.model_dump(exclude_none=True))
        arguments["organization"] = request.organization
        arguments["limit"] = min(
            int(arguments.get("limit", maximum_evidence)),
            maximum_evidence,
        )
        arguments["offset"] = max(0, int(arguments.get("offset", 0)))
        if request.job_id is not None:
            arguments["job_id"] = request.job_id
        return self._tools.search(EvidenceSearchInput.model_validate(arguments))

    @staticmethod
    def _validated_evidence_id(
        call: EvidenceAgentToolCall,
        request: EvidenceAgentRequest,
    ) -> UUID:
        value = call.arguments.get("evidence_id")
        if value is None:
            value = request.evidence_id
        evidence_id = UUID(str(value))
        if request.evidence_id is not None and evidence_id != request.evidence_id:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.INVALID_TOOL_REQUEST,
                "Tool request conflicts with the explicitly scoped evidence ID.",
            )
        return evidence_id

    @staticmethod
    def _scope_detail(
        result: AgentEvidenceDetailResult,
        organization: str,
    ) -> AgentEvidenceDetailResult:
        if result.found and result.detail is not None and result.detail.organization != organization:
            return AgentEvidenceDetailResult(found=False)
        return result

    @staticmethod
    def _scope_trace(result: EvidenceTrace, organization: str) -> EvidenceTrace:
        if result.found and result.organization != organization:
            return EvidenceTrace(
                found=False,
                evidence_id=result.evidence_id,
                limitations=["Evidence record not found in the requested organization."],
            )
        return result

    def _validate_answer(
        self,
        answer: EvidenceAgentAnswer,
        request: EvidenceAgentRequest,
        catalog: dict[UUID, _EvidenceCatalogEntry],
    ) -> None:
        if answer.status == EvidenceAgentStatus.ANSWERED and not answer.citations:
            raise EvidenceAgentError(
                EvidenceAgentFailureCode.CITATION_VALIDATION,
                "An evidence-backed answer must contain citations.",
            )
        for citation in answer.citations:
            entry = catalog.get(citation.evidence_id)
            if entry is None:
                raise EvidenceAgentError(
                    EvidenceAgentFailureCode.CITATION_VALIDATION,
                    "Citation references evidence not returned by an approved tool.",
                )
            if entry.organization != request.organization or entry.job_id != citation.job_id:
                raise EvidenceAgentError(
                    EvidenceAgentFailureCode.PROVENANCE_VALIDATION,
                    "Citation job/evidence provenance does not match tool results.",
                )
            if citation.relationship_type not in entry.relationships:
                raise EvidenceAgentError(
                    EvidenceAgentFailureCode.PROVENANCE_VALIDATION,
                    "Citation relationship is not present in tool results.",
                )
            if citation.source_type is not None and entry.source_type != citation.source_type:
                raise EvidenceAgentError(
                    EvidenceAgentFailureCode.PROVENANCE_VALIDATION,
                    "Citation source type does not match tool results.",
                )
            if citation.excerpt is not None and not excerpt_is_grounded(
                citation.excerpt,
                entry.excerpts,
            ):
                raise EvidenceAgentError(
                    EvidenceAgentFailureCode.CITATION_VALIDATION,
                    "Citation excerpt is not present in returned evidence.",
                )

    @staticmethod
    def _catalog_record(
        record: UnifiedEvidenceRecord,
        catalog: dict[UUID, _EvidenceCatalogEntry],
    ) -> None:
        entry = catalog.setdefault(
            record.evidence_id,
            _EvidenceCatalogEntry(
                job_id=record.job_id,
                organization=record.organization,
                source_type=record.source_type.value,
            ),
        )
        if record.evidence_preview:
            entry.excerpts.add(record.evidence_preview)
        source_excerpt = getattr(record, "source_excerpt", None)
        if source_excerpt:
            entry.excerpts.add(source_excerpt)
        if record.enrichment_present:
            entry.relationships.add(EvidenceRelationshipType.HIRING_ENRICHMENT)
        if record.related_hiring_signals:
            entry.relationships.add(EvidenceRelationshipType.HIRING_SIGNAL)
        if record.related_technology_observation_count:
            entry.relationships.add(EvidenceRelationshipType.TECHNOLOGY_OBSERVATION)
        if record.related_technology_signals:
            entry.relationships.add(EvidenceRelationshipType.TECHNOLOGY_SIGNAL)
        for observation in getattr(record, "technology_observations", []):
            if observation.support_excerpt:
                entry.excerpts.add(observation.support_excerpt)

    @staticmethod
    def _catalog_trace(
        trace: EvidenceTrace,
        catalog: dict[UUID, _EvidenceCatalogEntry],
    ) -> None:
        entry = catalog.setdefault(
            trace.evidence_id,
            _EvidenceCatalogEntry(
                job_id=trace.job_id,
                organization=trace.organization,
            ),
        )
        if trace.enrichment_present:
            entry.relationships.add(EvidenceRelationshipType.HIRING_ENRICHMENT)
        if trace.hiring_signals:
            entry.relationships.add(EvidenceRelationshipType.HIRING_SIGNAL)
        if trace.technology_observations:
            entry.relationships.add(EvidenceRelationshipType.TECHNOLOGY_OBSERVATION)
        if trace.technology_signals:
            entry.relationships.add(EvidenceRelationshipType.TECHNOLOGY_SIGNAL)
        if trace.cross_domain_signal_ids:
            entry.relationships.add(EvidenceRelationshipType.CROSS_DOMAIN_SIGNAL)

    @staticmethod
    def _reliability(
        answer: EvidenceAgentAnswer,
        catalog: dict[UUID, _EvidenceCatalogEntry],
        maximum_evidence: int,
    ) -> float:
        if not catalog:
            return 0.0
        if not answer.citations:
            return round(min(0.4, len(catalog) / maximum_evidence), 4)
        relationship_weights = {
            EvidenceRelationshipType.SOURCE_EVIDENCE: 1.0,
            EvidenceRelationshipType.HIRING_ENRICHMENT: 0.8,
            EvidenceRelationshipType.HIRING_SIGNAL: 0.7,
            EvidenceRelationshipType.TECHNOLOGY_OBSERVATION: 0.7,
            EvidenceRelationshipType.TECHNOLOGY_SIGNAL: 0.65,
            EvidenceRelationshipType.CROSS_DOMAIN_SIGNAL: 0.65,
        }
        source_quality = sum(
            relationship_weights[item.relationship_type] for item in answer.citations
        ) / len(answer.citations)
        independent_support = min(
            len({item.evidence_id for item in answer.citations}) / 3,
            1.0,
        )
        evidence_availability = min(len(catalog) / maximum_evidence, 1.0)
        return round(
            min(1.0, (source_quality + independent_support + evidence_availability) / 3),
            4,
        )

    def _tool_specs(self) -> list[EvidenceAgentToolSpec]:
        specs = []
        for name in ALLOWED_TOOLS:
            definition = self._registry.get(name)
            if definition is None or not definition.read_only:
                raise EvidenceAgentError(
                    EvidenceAgentFailureCode.INVALID_TOOL_REQUEST,
                    "Approved Evidence Agent tool metadata is unavailable.",
                )
            specs.append(
                EvidenceAgentToolSpec(
                    name=name,
                    description=definition.description,
                    input_schema=definition.input_model.model_json_schema(),
                )
            )
        return specs
