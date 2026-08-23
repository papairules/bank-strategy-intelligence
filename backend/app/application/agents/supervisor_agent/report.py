from pydantic import BaseModel, ConfigDict, Field

from .supervisor import SupervisorResponse
from .outlook import DeterministicIntelligenceOutlookMapper, IntelligenceOutlookRow


class ReportSupportReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: str
    domain: str
    evidence_ids: list[str] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)
    source_url: str | None = None


class ReportFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    narrative: str
    supporting_reference_ids: list[str] = Field(default_factory=list)


class ReportHorizon(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    horizon_days: int
    meaning: str
    opportunity_titles: list[str] = Field(default_factory=list)


class CompanyIntelligenceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    organization: str
    total_hiring_jobs: int = Field(default=0, ge=0)
    generated_at: str
    executive_summary: str
    strategic_priorities: list[ReportFinding] = Field(default_factory=list)
    hiring_intelligence: list[ReportFinding] = Field(default_factory=list)
    cross_domain_alignment: list[ReportFinding] = Field(default_factory=list)
    business_areas_to_watch: list[ReportFinding] = Field(default_factory=list)
    opportunity_horizons: list[ReportHorizon] = Field(default_factory=list)
    intelligence_outlook_rows: list[IntelligenceOutlookRow] = Field(default_factory=list)
    evidence_traceability: list[ReportSupportReference] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DeterministicReportGenerator:
    def __init__(self, outlook_mapper: DeterministicIntelligenceOutlookMapper | None = None) -> None:
        self._outlook_mapper = outlook_mapper or DeterministicIntelligenceOutlookMapper()

    def generate(self, normalized, supervisor: SupervisorResponse) -> CompanyIntelligenceReport:
        references = self._references(normalized, supervisor)
        reference_ids = {item.reference_id for item in references}
        priorities = [
            ReportFinding(
                title=item.priority,
                narrative=(
                    f"Strategic evidence suggests {item.explanation.rstrip('.')} "
                    "This is an evidence-backed interpretation, not confirmed causation."
                ),
                supporting_reference_ids=[
                    value for value in item.supporting_evidence_ids if value in reference_ids
                ],
            )
            for item in supervisor.client_priorities
        ]
        hiring = self._hiring_findings(normalized)
        alignment = self._alignment_findings(supervisor)
        business_areas = [
            ReportFinding(
                title=value.name,
                narrative=(
                    f"Observed hiring enrichment identifies {value.name} across "
                    f"{value.job_count} persisted-enriched job record(s); treat this as directional."
                ),
                supporting_reference_ids=[f"kg:business_unit:{value.key}"],
            )
            for value in normalized.hiring.kg_summary.observed_business_units
        ]
        horizons = [
            ReportHorizon(
                horizon_days=item.horizon_days,
                meaning=item.meaning,
                opportunity_titles=[value.title for value in item.opportunities],
            )
            for item in supervisor.horizons
        ]
        return CompanyIntelligenceReport(
            organization=normalized.organization,
            total_hiring_jobs=normalized.hiring.coverage.total_jobs,
            generated_at=supervisor.generated_at,
            executive_summary=supervisor.executive_summary,
            strategic_priorities=priorities,
            hiring_intelligence=hiring,
            cross_domain_alignment=alignment,
            business_areas_to_watch=business_areas,
            opportunity_horizons=horizons,
            intelligence_outlook_rows=self._outlook_mapper.map(normalized, supervisor),
            evidence_traceability=references,
            limitations=list(
                dict.fromkeys(
                    [
                        *supervisor.limitations,
                        *normalized.hiring.coverage.limitations,
                    ]
                )
            ),
        )

    @staticmethod
    def _hiring_findings(normalized) -> list[ReportFinding]:
        values = []
        for concept in normalized.hiring.kg_summary.observed_technologies:
            values.append(
                ReportFinding(
                    title=f"Observed technology: {concept.name}",
                    narrative=(
                        f"Persisted hiring data observed {concept.name} in "
                        f"{concept.job_count} job record(s). This is observed hiring evidence, "
                        "not proof of enterprise-wide investment or causation."
                    ),
                    supporting_reference_ids=[f"kg:technology:{concept.key}"],
                )
            )
        for generated in normalized.hiring.signals.signals:
            values.append(
                ReportFinding(
                    title=generated.title,
                    narrative=(
                        f"Observed hiring indicates {generated.signal.summary.rstrip('.')} "
                        "The signal describes public hiring activity, not confirmed investment."
                    ),
                    supporting_reference_ids=[str(generated.signal.signal_id)],
                )
            )
        return values

    @staticmethod
    def _alignment_findings(supervisor: SupervisorResponse) -> list[ReportFinding]:
        agent_by_id = {item.evidence_id: item.agent for item in supervisor.evidence}
        values = []
        for priority in supervisor.client_priorities:
            agents = {agent_by_id.get(value) for value in priority.supporting_evidence_ids}
            if {"strategy", "hiring"}.issubset(agents):
                values.append(
                    ReportFinding(
                        title=priority.priority,
                        narrative=(
                            "Strategy and observed hiring evidence appear aligned around this priority; "
                            "the relationship is correlational rather than causal."
                        ),
                        supporting_reference_ids=priority.supporting_evidence_ids,
                    )
                )
        return values

    @staticmethod
    def _references(normalized, supervisor: SupervisorResponse) -> list[ReportSupportReference]:
        values = [
            ReportSupportReference(
                reference_id=item.evidence_id,
                domain=item.agent,
                evidence_ids=[item.evidence_id],
                source_url=item.source_url,
            )
            for item in supervisor.evidence
        ]
        kg = normalized.hiring.kg_summary
        for concept_type, concepts in (
            ("technology", kg.observed_technologies),
            ("business_unit", kg.observed_business_units),
            ("capability", kg.observed_capabilities),
        ):
            for concept in concepts:
                values.append(
                    ReportSupportReference(
                        reference_id=f"kg:{concept_type}:{concept.key}",
                        domain="hiring_kg",
                        evidence_ids=concept.supporting_evidence_ids,
                        job_ids=concept.supporting_job_ids,
                    )
                )
        return list({item.reference_id: item for item in values}.values())
