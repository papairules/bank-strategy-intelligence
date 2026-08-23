import asyncio
import json
import logging
import re
from collections.abc import Callable
from datetime import date
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError

from backend.app.application.agents.registry import AgentToolRegistry
from backend.app.application.agents.strategy_agent.models import (
    StrategyAgentError,
    StrategyAgentFailureCode,
    StrategyAgentRequest,
    StrategyAgentResult,
    StrategyAgentStatus,
    StrategyFinding,
    StrategyProviderRequest,
    StrategyProviderResponse,
    StrategyProviderStage,
    StrategySupportClass,
    StrategySupportReference,
    StrategyToolCall,
    StrategyToolResult,
    StrategyToolSpec,
    StrategyAgentOutput,
)
from backend.app.application.agents.strategy_agent.prompts import STRATEGY_AGENT_SYSTEM_POLICY
from backend.app.application.agents.strategy_agent.provider import StrategyAgentProvider
from backend.app.application.agents.strategy_agent.validation import (
    contains_unsupported_intent_claim,
    contains_unsupported_support_narrowing,
)
from backend.app.application.agents.strategy_agent.graph import initial_state


logger = logging.getLogger(__name__)

_ORGANIZATION_ALIASES = {
    "Wells Fargo": ("wells fargo",),
    "Goldman Sachs": ("goldman sachs", "goldman"),
    "BNY": ("bank of new york mellon", "bny mellon", "bny"),
    "Citibank": ("citibank", "citi", "citigroup"),
    "Morgan Stanley": ("morgan stanley",),
    "Barclays": ("barclays",),
}


def _canonical_organization(name: str) -> str | None:
    normalized = " ".join(name.casefold().split())
    return next(
        (
            canonical
            for canonical, aliases in _ORGANIZATION_ALIASES.items()
            if normalized in aliases
        ),
        None,
    )


def _organizations_named_in(question: str) -> set[str]:
    named: set[str] = set()
    for canonical, aliases in _ORGANIZATION_ALIASES.items():
        if any(
            re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", question, re.IGNORECASE)
            for alias in aliases
        ):
            named.add(canonical)
    return named


def _validate_organization_scope(organization: str, question: str) -> None:
    selected = _canonical_organization(organization)
    if selected is None:
        return
    mismatches = sorted(_organizations_named_in(question) - {selected})
    if not mismatches:
        return
    target = ", ".join(mismatches)
    raise StrategyAgentError(
        StrategyAgentFailureCode.ORGANIZATION_SCOPE_MISMATCH,
        f"The question targets {target}, but the current data scope is {selected}. "
        f"Switch the Current Data Scope to {target} or ask about {selected}.",
    )


class StrategyToolBundle(Protocol):
    hiring: object
    technology: object
    evidence: object
    strategy: object
    registry: AgentToolRegistry


class StrategyAgentService:
    AGENT_VERSION = "strategy-orchestrator-v1"

    def __init__(
        self,
        tools: StrategyToolBundle,
        provider: StrategyAgentProvider,
        *,
        enabled: bool = False,
        max_tool_calls: int = 6,
        max_search_results: int = 10,
        max_evidence_records: int = 10,
        max_payload_chars: int = 100_000,
    ) -> None:
        self._tools = tools
        self._provider = provider
        self._enabled = enabled
        self._max_tool_calls = max_tool_calls
        self._max_search_results = max_search_results
        self._max_evidence_records = max_evidence_records
        self._max_payload_chars = max_payload_chars
        self._definitions = {item.name: item for item in tools.registry.list() if item.read_only}

    async def answer(self, request: StrategyAgentRequest) -> StrategyAgentResult:
        if not self._enabled:
            raise StrategyAgentError(StrategyAgentFailureCode.DISABLED, "Strategy Agent is disabled.")
        specs = [
            StrategyToolSpec(
                name=item.name,
                description=item.description,
                input_schema=item.input_model.model_json_schema(),
            )
            for item in self._definitions.values()
        ]
        plan = await self._provider.respond(
            StrategyProviderRequest(
                stage=StrategyProviderStage.PLAN,
                system_policy=STRATEGY_AGENT_SYSTEM_POLICY,
                request=request,
                allowed_tools=specs,
            )
        )
        calls = self._validate_plan(plan)
        results = [self._execute(call, request.organization) for call in calls]
        self._enforce_payload_limit(results)
        references = self._create_references(results)
        final = await self._provider.respond(
            StrategyProviderRequest(
                stage=StrategyProviderStage.ANSWER,
                system_policy=STRATEGY_AGENT_SYSTEM_POLICY,
                request=request,
                allowed_tools=[],
                tool_results=results,
                support_references=references,
            )
        )
        return self._reconstruct(request, final, results, references)

    def _validate_plan(self, response: StrategyProviderResponse) -> list[StrategyToolCall]:
        if response.output is not None:
            raise StrategyAgentError(StrategyAgentFailureCode.MALFORMED_PROVIDER_OUTPUT, "Planning response included an answer.")
        unique: list[StrategyToolCall] = []
        seen: set[tuple[str, str]] = set()
        for call in response.tool_calls:
            if call.name not in self._definitions:
                raise StrategyAgentError(StrategyAgentFailureCode.INVALID_TOOL_REQUEST, "Provider requested an unapproved tool.")
            key = (call.name, json.dumps(call.arguments, sort_keys=True))
            if key not in seen:
                seen.add(key)
                unique.append(call)
        if len(unique) > self._max_tool_calls:
            raise StrategyAgentError(StrategyAgentFailureCode.TOOL_EXECUTION_LIMIT, "Provider exceeded the tool execution limit.")
        return unique

    def _execute(self, call: StrategyToolCall, organization: str) -> StrategyToolResult:
        definition = self._definitions[call.name]
        arguments = dict(call.arguments)
        if "organization" in definition.input_model.model_fields:
            arguments["organization"] = organization
        if "limit" in definition.input_model.model_fields:
            arguments["limit"] = min(int(arguments.get("limit", self._max_search_results)), self._max_search_results)
        try:
            validated = definition.input_model.model_validate(arguments)
        except (ValidationError, TypeError, ValueError) as exc:
            raise StrategyAgentError(StrategyAgentFailureCode.INVALID_TOOL_REQUEST, "Provider supplied invalid tool arguments.") from exc
        try:
            output = self._dispatch(call.name)(validated)
        except StrategyAgentError:
            raise
        except Exception as exc:
            raise StrategyAgentError(StrategyAgentFailureCode.TOOL_EXECUTION_FAILURE, "An approved intelligence tool failed.") from exc
        payload = output.model_dump(mode="json") if isinstance(output, BaseModel) else output
        payload = self._enforce_organization_scope(call.name, payload, organization)
        return StrategyToolResult(call_id=call.call_id, name=call.name, result=payload)

    def _dispatch(self, name: str) -> Callable:
        domain, operation = name.split(".", 1)
        return getattr(getattr(self._tools, domain), operation)

    @staticmethod
    def _enforce_organization_scope(name: str, payload: dict, organization: str) -> dict:
        found_organization = payload.get("organization")
        if found_organization and found_organization.casefold() != organization.casefold():
            if name == "hiring.get_job_intelligence":
                return {"found": False, "enrichment": {"available": False}}
            if name in {"evidence.get", "evidence.trace"}:
                return {"found": False, "limitations": ["Record is unavailable in the requested organization scope."]}
            raise StrategyAgentError(StrategyAgentFailureCode.PROVENANCE_VALIDATION, "Tool result crossed organization scope.")
        return payload

    def _enforce_payload_limit(self, results: list[StrategyToolResult]) -> None:
        size = len(json.dumps([item.model_dump(mode="json") for item in results], sort_keys=True))
        if size > self._max_payload_chars:
            raise StrategyAgentError(StrategyAgentFailureCode.PAYLOAD_LIMIT, "Trusted tool-result payload exceeded its configured bound.")

    def _create_references(self, results: list[StrategyToolResult]) -> list[StrategySupportReference]:
        references: list[StrategySupportReference] = []
        for result in results:
            support_classes = self._support_classes(result.name, result.result)
            evidence_ids = self._collect_uuids(result.result, {"evidence_id", "supporting_evidence_ids"})[: self._max_evidence_records]
            job_ids = self._collect_uuids(result.result, {"job_id", "supporting_job_ids", "contributing_job_ids"})
            signal_ids = self._collect_uuids(result.result, {"signal_id", "related_signal_ids"})
            for support_class in support_classes:
                references.append(
                    StrategySupportReference(
                        reference=f"strategy_ref_{len(references) + 1}",
                        domain=result.name.split(".", 1)[0],
                        support_class=support_class,
                        tool_name=result.name,
                        evidence_ids=evidence_ids,
                        job_ids=job_ids,
                        signal_ids=signal_ids,
                    )
                )
        return references

    @staticmethod
    def _support_classes(name: str, payload: dict) -> list[StrategySupportClass]:
        if name.endswith("get_signals"):
            return [StrategySupportClass.DERIVED_SIGNAL]
        if name.startswith("evidence."):
            classes = [StrategySupportClass.SOURCE_EVIDENCE]
            serialized = json.dumps(payload, sort_keys=True).lower()
            if '"enrichment_present": true' in serialized or '"available": true' in serialized:
                classes.append(StrategySupportClass.AI_ENRICHMENT)
            if "technology_observation" in serialized or "related_hiring_signals" in serialized:
                classes.append(StrategySupportClass.DERIVED_ANALYTICS)
            return classes
        if name == "hiring.get_job_intelligence" and payload.get("enrichment", {}).get("available"):
            return [StrategySupportClass.SOURCE_EVIDENCE, StrategySupportClass.AI_ENRICHMENT]
        return [StrategySupportClass.DERIVED_ANALYTICS]

    @classmethod
    def _collect_uuids(cls, value, keys: set[str]) -> list[UUID]:
        found: set[UUID] = set()
        def visit(item, key: str | None = None) -> None:
            if isinstance(item, dict):
                for child_key, child in item.items():
                    visit(child, child_key)
            elif isinstance(item, list):
                for child in item:
                    visit(child, key)
            elif key in keys:
                try:
                    found.add(UUID(str(item)))
                except (ValueError, TypeError):
                    pass
        visit(value)
        return sorted(found, key=str)

    def _reconstruct(
        self,
        request: StrategyAgentRequest,
        response: StrategyProviderResponse,
        results: list[StrategyToolResult],
        references: list[StrategySupportReference],
    ) -> StrategyAgentResult:
        if response.tool_calls or response.output is None:
            raise StrategyAgentError(StrategyAgentFailureCode.MALFORMED_PROVIDER_OUTPUT, "Answer response did not contain only a structured answer.")
        output = response.output
        if contains_unsupported_intent_claim(output.executive_summary):
            raise StrategyAgentError(StrategyAgentFailureCode.CLAIM_VALIDATION, "Executive summary asserted unsupported corporate intent.")
        if contains_unsupported_support_narrowing(output.executive_summary, []):
            raise StrategyAgentError(
                StrategyAgentFailureCode.CLAIM_VALIDATION,
                "Executive summary narrowed intelligence beyond uncited application support.",
            )
        trusted = {item.reference: item for item in references}
        findings: list[StrategyFinding] = []
        for item in output.findings:
            if contains_unsupported_intent_claim(item.statement):
                raise StrategyAgentError(StrategyAgentFailureCode.CLAIM_VALIDATION, "Finding asserted unsupported corporate intent.")
            selected: list[StrategySupportReference] = []
            seen: set[str] = set()
            for reference in item.citation_references:
                if reference not in trusted:
                    raise StrategyAgentError(StrategyAgentFailureCode.REFERENCE_VALIDATION, "Provider selected an unknown support reference.")
                if reference not in seen:
                    seen.add(reference)
                    selected.append(trusted[reference])
            if contains_unsupported_support_narrowing(item.statement, selected):
                raise StrategyAgentError(
                    StrategyAgentFailureCode.CLAIM_VALIDATION,
                    "Finding narrowed trusted support beyond its established intelligence domain.",
                )
            if contains_unsupported_support_narrowing(item.title, selected):
                raise StrategyAgentError(
                    StrategyAgentFailureCode.CLAIM_VALIDATION,
                    "Finding title narrowed trusted support beyond its established intelligence domain.",
                )
            findings.append(StrategyFinding(title=item.title, statement=item.statement, support=selected))
        limitations = self._limitations(output.limitations, results)
        status = StrategyAgentStatus.ANSWERED if findings else StrategyAgentStatus.INSUFFICIENT_EVIDENCE
        reliability = self._reliability(findings, results, status)
        return StrategyAgentResult(
            status=status,
            organization=request.organization,
            question=request.question,
            executive_summary=output.executive_summary,
            findings=findings,
            reliability=reliability,
            limitations=limitations,
            tool_calls_used=len(results),
            provider=response.provider,
            model=response.model,
            agent_version=response.agent_version,
        )

    @classmethod
    def _limitations(cls, provider_limitations: list[str], results: list[StrategyToolResult]) -> list[str]:
        values = list(provider_limitations)
        def visit(value, key=None):
            if isinstance(value, dict):
                for child_key, child in value.items(): visit(child, child_key)
            elif isinstance(value, list):
                if key == "limitations": values.extend(str(item) for item in value if isinstance(item, str))
                else:
                    for item in value: visit(item, key)
        for result in results: visit(result.result)
        return list(dict.fromkeys(item.strip() for item in values if item.strip()))

    @staticmethod
    def _reliability(findings: list[StrategyFinding], results: list[StrategyToolResult], status: StrategyAgentStatus) -> float:
        supports = [support for finding in findings for support in finding.support]
        weights = {
            StrategySupportClass.SOURCE_EVIDENCE: 0.9,
            StrategySupportClass.AI_ENRICHMENT: 0.6,
            StrategySupportClass.DERIVED_ANALYTICS: 0.7,
            StrategySupportClass.DERIVED_SIGNAL: 0.8,
        }
        quality = sum(weights[item.support_class] for item in supports) / len(supports) if supports else 0.0
        jobs = {job_id for item in supports for job_id in item.job_ids}
        independent = min(len(jobs) / 5, 1.0)
        evidence_coverage = enrichment_coverage = observation = 0.0
        for result in results:
            if result.name == "strategy.get_context":
                evidence_coverage = float(result.result.get("evidence_coverage", 0))
                enrichment_coverage = float(result.result.get("enrichment_coverage", 0))
                start, end = result.result.get("observation_start"), result.result.get("observation_end")
                if start and end:
                    observation = min((date.fromisoformat(end) - date.fromisoformat(start)).days / 30, 1.0)
        citation_coverage = 1.0 if findings and all(item.support for item in findings) else 0.0
        score = 0.25 * quality + 0.2 * independent + 0.2 * evidence_coverage + 0.15 * enrichment_coverage + 0.1 * observation + 0.1 * citation_coverage
        if status == StrategyAgentStatus.INSUFFICIENT_EVIDENCE:
            score = min(score, 0.35)
        return round(max(0.0, min(score, 1.0)), 4)


class IntegratedStrategyAgentService:
    """Async FastAPI boundary and compatibility adapter for the LangGraph agent."""

    AGENT_VERSION = "strategy-langgraph-v1"

    def __init__(
        self,
        graph,
        *,
        enabled: bool = False,
        model: str,
        api_key_configured: bool = True,
    ) -> None:
        self._graph = graph
        self._enabled = enabled
        self._model = model
        self._api_key_configured = api_key_configured

    async def answer(self, request: StrategyAgentRequest) -> StrategyAgentResult:
        _validate_organization_scope(request.organization, request.question)
        if not self._enabled:
            raise StrategyAgentError(
                StrategyAgentFailureCode.DISABLED,
                "Strategy Agent is disabled.",
            )
        if not self._api_key_configured:
            raise StrategyAgentError(
                StrategyAgentFailureCode.AUTHENTICATION,
                "OpenAI API credentials are not configured.",
            )
        logger.info("[integrated_strategy] organization=%s", request.organization)
        state = initial_state(
            company=request.organization,
            question=request.question,
            time_horizon=request.time_horizon,
        )
        try:
            result = await asyncio.to_thread(self._graph.invoke, state)
            output = StrategyAgentOutput.model_validate(result["final_output"])
        except StrategyAgentError:
            raise
        except Exception as exc:
            raise StrategyAgentError(
                StrategyAgentFailureCode.PROVIDER_UNAVAILABLE,
                "Integrated OpenAI Strategy Agent execution failed.",
                metadata={"error_type": type(exc).__name__},
            ) from exc
        signals = output.strategic_signals
        findings = [
            StrategyFinding(
                title=signal.priority,
                statement=signal.hypothesis,
                support=[],
            )
            for signal in signals
        ]
        reliability = (
            round(sum(signal.confidence for signal in signals) / len(signals), 4)
            if signals
            else 0.0
        )
        status = (
            StrategyAgentStatus.ANSWERED
            if signals
            else StrategyAgentStatus.INSUFFICIENT_EVIDENCE
        )
        if signals:
            themes = ", ".join(signal.priority for signal in signals)
            executive_summary = (
                f"Evidence-backed research identified {len(signals)} supported strategic "
                f"theme{'s' if len(signals) != 1 else ''}: {themes}."
            )
            limitations: list[str] = []
        else:
            executive_summary = output.message or (
                "Insufficient evidence to identify a reliable strategic direction."
            )
            limitations = [executive_summary]
        logger.info(
            "[strategy_adapter] produced %d compatibility findings", len(findings)
        )
        return StrategyAgentResult(
            status=status,
            organization=request.organization,
            question=request.question,
            executive_summary=executive_summary,
            findings=findings,
            reliability=reliability,
            limitations=limitations,
            tool_calls_used=len(result.get("research_queries", [])),
            provider="openai",
            model=self._model,
            agent_version=self.AGENT_VERSION,
            strategic_signals=signals,
        )
