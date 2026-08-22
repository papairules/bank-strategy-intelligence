import asyncio
from collections.abc import Callable
from enum import StrEnum
import re
from typing import Any, Protocol

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.application.agents.strategy_agent import (
    IntegratedStrategyAgentService,
    StrategyAgentRequest,
    StrategyAgentResult,
)
from backend.app.application.hiring import (
    HiringReadServiceProtocol,
    HiringSignalGenerationResult,
)
from backend.app.application.hiring.kg import (
    HiringKGEdgeType,
    HiringKGNodeType,
    HiringKnowledgeGraphService,
    get_business_units_for_organization,
    get_capabilities_for_organization,
    get_evidence_for_job,
    get_jobs_for_capability,
    get_jobs_for_technology,
    get_jobs_supporting_hiring_signal,
    get_technologies_for_organization,
    summarize_hiring_knowledge_graph,
)
from backend.app.domain.organization import organization_key

from .report import CompanyIntelligenceReport, DeterministicReportGenerator
from .supervisor import (
    CompanyContext,
    CompanyScopeError,
    SupervisorRequest,
    SupervisorResponse,
)


class SupervisorRuntimeFailureCode(StrEnum):
    DISABLED = "disabled_agent"
    ORGANIZATION_SCOPE_MISMATCH = "organization_scope_mismatch"
    SPECIALIST_FAILURE = "specialist_failure"
    SUPERVISOR_FAILURE = "supervisor_failure"


class SupervisorRuntimeError(Exception):
    def __init__(self, code: SupervisorRuntimeFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class SupervisorReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1, max_length=200)
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    time_horizon: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_blank_values(self):
        if not self.organization.strip():
            raise ValueError("organization must contain non-whitespace text")
        if self.question is not None and not self.question.strip():
            raise ValueError("question must contain non-whitespace text")
        return self


class HiringCoverageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization: str
    total_jobs: int = Field(ge=0)
    enriched_jobs: int = Field(ge=0)
    enrichment_coverage_percentage: float = Field(ge=0, le=100)
    kg_enriched_job_count: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)


class ObservedKGConcept(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    name: str
    job_count: int = Field(ge=1)
    supporting_job_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    all_supporting_job_ids: list[str] = Field(default_factory=list, exclude=True, repr=False)


class ObservedHiringSignalSupport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: str
    job_count: int = Field(ge=1)
    supporting_job_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    all_supporting_job_ids: list[str] = Field(default_factory=list, exclude=True, repr=False)


class CompactHiringKGSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    enriched_jobs_used: int = Field(ge=0)
    observed_technologies: list[ObservedKGConcept] = Field(default_factory=list)
    observed_business_units: list[ObservedKGConcept] = Field(default_factory=list)
    observed_capabilities: list[ObservedKGConcept] = Field(default_factory=list)
    observed_hiring_signals: list[ObservedHiringSignalSupport] = Field(default_factory=list)
    selected_supporting_job_ids: list[str] = Field(default_factory=list)
    selected_supporting_evidence_ids: list[str] = Field(default_factory=list)


class NormalizedStrategyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    output: StrategyAgentResult


class NormalizedHiringInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    signals: HiringSignalGenerationResult
    coverage: HiringCoverageMetadata
    kg_summary: CompactHiringKGSummary


class NormalizedSupervisorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    question: str
    time_horizon: str | None = None
    strategy: NormalizedStrategyInput
    hiring: NormalizedHiringInput


class SupervisorReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    strategy_signal_count: int = Field(ge=0)
    hiring_signal_count: int = Field(ge=0)
    coverage: HiringCoverageMetadata
    kg_summary: CompactHiringKGSummary
    supervisor: SupervisorResponse
    report: CompanyIntelligenceReport
    provider: str
    model: str


class HiringSignalBoundary(Protocol):
    def generate(self, organization: str) -> HiringSignalGenerationResult: ...


_ORGANIZATIONS = {
    "Wells Fargo": ("wells fargo",),
    "Goldman Sachs": ("goldman sachs", "goldman"),
    "BNY": ("bny", "bny mellon", "bank of new york mellon"),
    "Citibank": ("citibank", "citi", "citigroup"),
    "Morgan Stanley": ("morgan stanley",),
    "Barclays": ("barclays",),
}


def validate_report_question_scope(organization: str, question: str) -> None:
    selected = next(
        (name for name, aliases in _ORGANIZATIONS.items() if organization.casefold().strip() in aliases),
        organization.strip(),
    )
    named = {
        name
        for name, aliases in _ORGANIZATIONS.items()
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", question, re.I) for alias in aliases)
    }
    mismatches = sorted(named - {selected})
    if mismatches:
        target = ", ".join(mismatches)
        raise SupervisorRuntimeError(
            SupervisorRuntimeFailureCode.ORGANIZATION_SCOPE_MISMATCH,
            f"The question targets {target}, but the current data scope is {selected}. "
            f"Switch the Current Data Scope to {target} or ask about {selected}.",
        )


class SupervisorAppService:
    def __init__(
        self,
        *,
        strategy_service: IntegratedStrategyAgentService,
        hiring_signals: HiringSignalBoundary,
        hiring_read: HiringReadServiceProtocol,
        hiring_kg: HiringKnowledgeGraphService,
        supervisor_runner: Callable[[SupervisorRequest], SupervisorResponse],
        report_generator: DeterministicReportGenerator | None = None,
        enabled: bool = False,
        provider: str = "openai",
        model: str,
    ) -> None:
        self._strategy = strategy_service
        self._hiring_signals = hiring_signals
        self._read = hiring_read
        self._kg = hiring_kg
        self._supervisor_runner = supervisor_runner
        self._report_generator = report_generator or DeterministicReportGenerator()
        self._enabled = enabled
        self._provider = provider
        self._model = model

    async def generate_report(self, request: SupervisorReportRequest) -> SupervisorReportResult:
        if not self._enabled:
            raise SupervisorRuntimeError(
                SupervisorRuntimeFailureCode.DISABLED, "Supervisor Report is disabled."
            )
        organization = request.organization.strip()
        question = request.question or f"Generate a company intelligence report for {organization}."
        validate_report_question_scope(organization, question)
        try:
            strategy = await self._strategy.answer(
                StrategyAgentRequest(
                    organization=organization,
                    question=question,
                    time_horizon=request.time_horizon,
                )
            )
            graph, hiring_signals = await asyncio.gather(
                asyncio.to_thread(self._kg.build_for_organization, organization),
                asyncio.to_thread(self._hiring_signals.generate, organization),
            )
        except SupervisorRuntimeError:
            raise
        except Exception as error:
            raise SupervisorRuntimeError(
                SupervisorRuntimeFailureCode.SPECIALIST_FAILURE,
                "A specialist intelligence service could not complete the report.",
            ) from error
        normalized = self._normalize(organization, question, request.time_horizon, strategy, hiring_signals, graph)
        self._validate_normalized_scope(normalized)
        try:
            supervisor = await asyncio.to_thread(
                self._supervisor_runner, self._legacy_request(normalized)
            )
        except CompanyScopeError as error:
            raise SupervisorRuntimeError(
                SupervisorRuntimeFailureCode.ORGANIZATION_SCOPE_MISMATCH, str(error)
            ) from error
        except Exception as error:
            raise SupervisorRuntimeError(
                SupervisorRuntimeFailureCode.SUPERVISOR_FAILURE,
                "Supervisor synthesis could not complete the report.",
            ) from error
        if supervisor.company_name != organization:
            raise SupervisorRuntimeError(
                SupervisorRuntimeFailureCode.ORGANIZATION_SCOPE_MISMATCH,
                "Supervisor output did not match the selected organization.",
            )
        supervisor.limitations = list(
            dict.fromkeys([*supervisor.limitations, *normalized.hiring.coverage.limitations])
        )
        report = self._report_generator.generate(normalized, supervisor)
        return SupervisorReportResult(
            organization=organization,
            strategy_signal_count=len(strategy.strategic_signals),
            hiring_signal_count=len(hiring_signals.signals),
            coverage=normalized.hiring.coverage,
            kg_summary=normalized.hiring.kg_summary,
            supervisor=supervisor,
            report=report,
            provider=self._provider,
            model=self._model,
        )

    def _normalize(self, organization, question, time_horizon, strategy, signals, graph):
        summary = summarize_hiring_knowledge_graph(graph)
        coverage_value = summary.enriched_jobs_used / summary.jobs_read * 100 if summary.jobs_read else 0
        limitations = []
        if summary.jobs_read == 0:
            limitations.append(f"No persisted {organization} hiring jobs are available for enrichment coverage.")
        elif summary.enriched_jobs_used < summary.jobs_read:
            limitations.append(
                f"Persisted hiring enrichment currently covers {summary.enriched_jobs_used} of "
                f"{summary.jobs_read} {organization} jobs ({coverage_value:.2f}%); enrichment-derived "
                "technology/capability relationships should be treated as directional rather than comprehensive."
            )
        coverage = HiringCoverageMetadata(
            organization=organization,
            total_jobs=summary.jobs_read,
            enriched_jobs=summary.enriched_jobs_used,
            enrichment_coverage_percentage=round(coverage_value, 4),
            kg_enriched_job_count=summary.enriched_jobs_used,
            limitations=limitations,
        )
        kg = compact_hiring_kg_summary(graph)
        return NormalizedSupervisorInput(
            organization=organization,
            question=question,
            time_horizon=time_horizon,
            strategy=NormalizedStrategyInput(organization=organization, output=strategy),
            hiring=NormalizedHiringInput(
                organization=organization, signals=signals, coverage=coverage, kg_summary=kg
            ),
        )

    @staticmethod
    def _validate_normalized_scope(value: NormalizedSupervisorInput) -> None:
        organizations = {
            value.organization,
            value.strategy.organization,
            value.strategy.output.organization,
            value.hiring.organization,
            value.hiring.signals.organization,
            value.hiring.coverage.organization,
            value.hiring.kg_summary.organization,
        }
        if organizations != {value.organization}:
            raise SupervisorRuntimeError(
                SupervisorRuntimeFailureCode.ORGANIZATION_SCOPE_MISMATCH,
                "Normalized intelligence inputs did not match the selected organization.",
            )

    @staticmethod
    def _legacy_request(value: NormalizedSupervisorInput) -> SupervisorRequest:
        organization = value.organization
        aliases = list(_ORGANIZATIONS.get(organization, (organization.casefold(),)))
        excluded = [name for name in _ORGANIZATIONS if name != organization]
        hiring_evidence = [
            {
                "evidence_id": str(item.signal.signal_id),
                "company_id": organization,
                "topic": item.signal.signal_type,
                "statement": item.signal.summary,
                "confidence": item.signal.confidence,
            }
            for item in value.hiring.signals.signals
        ]
        coverage_statement = (
            value.hiring.coverage.limitations[0]
            if value.hiring.coverage.limitations
            else f"Persisted hiring enrichment covers {value.hiring.coverage.enriched_jobs} of "
                 f"{value.hiring.coverage.total_jobs} {organization} jobs "
                 f"({value.hiring.coverage.enrichment_coverage_percentage:.2f}%)."
        )
        hiring_evidence.append(
            {
                "evidence_id": "HIRING_COVERAGE",
                "company_id": organization,
                "topic": "enrichment coverage",
                "statement": coverage_statement,
                "confidence": 1.0,
            }
        )
        for concept_type, concepts in (
            ("technology", value.hiring.kg_summary.observed_technologies),
            ("business unit", value.hiring.kg_summary.observed_business_units),
            ("capability", value.hiring.kg_summary.observed_capabilities),
        ):
            hiring_evidence.extend(
                {
                    "evidence_id": f"KG_{concept_type.upper().replace(' ', '_')}_{item.key}",
                    "company_id": organization,
                    "topic": concept_type,
                    "statement": (
                        f"Persisted hiring enrichment observed {item.name} across "
                        f"{item.job_count} job record(s); this is directional, not comprehensive."
                    ),
                    "confidence": 0.5,
                }
                for item in concepts
            )
        return SupervisorRequest(
            company_context=CompanyContext(
                company_id=organization_key(organization).upper(),
                canonical_name=organization,
                aliases=aliases,
                excluded_entities=excluded,
            ),
            question=value.question,
            time_horizon=value.time_horizon,
            mode="report",
            strategy_output=value.strategy.output.model_dump(mode="json"),
            hiring_output={
                "company": organization,
                "evidence": hiring_evidence,
                "coverage": value.hiring.coverage.model_dump(mode="json"),
                "kg_summary": value.hiring.kg_summary.model_dump(mode="json"),
            },
        )


def compact_hiring_kg_summary(graph: nx.MultiDiGraph) -> CompactHiringKGSummary:
    organization = graph.graph["organization"]

    def concepts(node_type, values, job_query):
        results = []
        for name in values(graph):
            jobs = job_query(graph, name)
            evidence = sorted(
                {str(item) for job_id in jobs for item in get_evidence_for_job(graph, job_id)}
            )
            results.append(
                ObservedKGConcept(
                    key=re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_"),
                    name=name,
                    job_count=len(jobs),
                    supporting_job_ids=[str(item) for item in jobs[:10]],
                    supporting_evidence_ids=evidence[:10],
                    all_supporting_job_ids=[str(item) for item in jobs],
                )
            )
        return results

    technologies = concepts(
        HiringKGNodeType.TECHNOLOGY,
        get_technologies_for_organization,
        get_jobs_for_technology,
    )
    capabilities = concepts(
        HiringKGNodeType.CAPABILITY,
        get_capabilities_for_organization,
        get_jobs_for_capability,
    )
    business_units = []
    for name in get_business_units_for_organization(graph):
        node_ids = [
            node
            for node, attributes in graph.nodes(data=True)
            if attributes.get("node_type") == HiringKGNodeType.BUSINESS_UNIT.value
            and attributes.get("value") == name
        ]
        jobs = sorted(
            {
                graph.nodes[source]["job_id"]
                for node in node_ids
                for source, _, edge in graph.in_edges(node, data=True)
                if edge.get("edge_type") == HiringKGEdgeType.BELONGS_TO.value
            }
        )
        evidence = sorted(
            {str(item) for job_id in jobs for item in get_evidence_for_job(graph, job_id)}
        )
        business_units.append(
            ObservedKGConcept(
                key=re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_"),
                name=name,
                job_count=len(jobs),
                supporting_job_ids=jobs[:10],
                supporting_evidence_ids=evidence[:10],
                all_supporting_job_ids=[str(item) for item in jobs],
            )
        )
    enriched_jobs = sorted(
        {
            graph.nodes[source]["job_id"]
            for source, _, edge in graph.edges(data=True)
            if edge.get("derivation_type") == "latest_persisted_enrichment"
            and graph.nodes[source].get("node_type") == HiringKGNodeType.JOB.value
        }
    )
    selected_evidence = sorted(
        {str(item) for job_id in enriched_jobs for item in get_evidence_for_job(graph, job_id)}
    )
    summary = summarize_hiring_knowledge_graph(graph)
    signal_support = []
    for node, attributes in graph.nodes(data=True):
        if attributes.get("node_type") != HiringKGNodeType.HIRING_SIGNAL.value:
            continue
        signal_id = attributes["signal_id"]
        jobs = get_jobs_supporting_hiring_signal(graph, signal_id)
        evidence = sorted({str(item) for job in jobs for item in get_evidence_for_job(graph, job)})
        if jobs:
            signal_support.append(ObservedHiringSignalSupport(
                signal_id=signal_id,
                job_count=len(jobs),
                supporting_job_ids=[str(item) for item in jobs[:10]],
                supporting_evidence_ids=evidence[:10],
                all_supporting_job_ids=[str(item) for item in jobs],
            ))
    return CompactHiringKGSummary(
        organization=organization,
        node_count=summary.node_count,
        edge_count=summary.edge_count,
        enriched_jobs_used=summary.enriched_jobs_used,
        observed_technologies=technologies,
        observed_business_units=business_units,
        observed_capabilities=capabilities,
        observed_hiring_signals=sorted(signal_support, key=lambda item: item.signal_id),
        selected_supporting_job_ids=enriched_jobs[:10],
        selected_supporting_evidence_ids=selected_evidence[:10],
    )
