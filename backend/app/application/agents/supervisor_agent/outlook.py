from pydantic import BaseModel, ConfigDict, Field

from .supervisor import Opportunity, SupervisorResponse, normalize_name


class IntelligenceOutlookRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_theme: str
    supervisor_priority: str
    opportunity_titles: list[str] = Field(default_factory=list)
    relevant_hiring_jobs: int | None = Field(default=None, ge=0)
    supporting_evidence_count: int = Field(default=0, ge=0)
    supporting_job_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    strategy_evidence_ids: list[str] = Field(default_factory=list)
    hiring_evidence_ids: list[str] = Field(default_factory=list)
    hiring_signal_ids: list[str] = Field(default_factory=list)
    kg_concept_references: list[str] = Field(default_factory=list)
    horizon_30: str | None = None
    horizon_60: str | None = None
    horizon_90: str | None = None
    horizon_180: str | None = None
    horizon_360: str | None = None
    confidence: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=100)
    limitations: list[str] = Field(default_factory=list)


class DeterministicIntelligenceOutlookMapper:
    def map(self, normalized, supervisor: SupervisorResponse) -> list[IntelligenceOutlookRow]:
        evidence_agent = {item.evidence_id: item.agent for item in supervisor.evidence}
        support_index = self._hiring_support_index(normalized)
        grouped: dict[str, list[Opportunity]] = {}
        for section in supervisor.horizons:
            for opportunity in section.opportunities:
                grouped.setdefault(normalize_name(opportunity.client_priority), []).append(opportunity)
        ranked = sorted(
            grouped.values(),
            key=lambda values: (-max(item.score for item in values), values[0].client_priority.casefold()),
        )[:5]
        return [self._row(values, evidence_agent, support_index) for values in ranked]

    @staticmethod
    def _hiring_support_index(normalized) -> dict[str, tuple[list[str], list[str], list[str], str]]:
        summary = normalized.hiring.kg_summary
        values: dict[str, tuple[list[str], list[str], list[str], str]] = {}
        for signal in summary.observed_hiring_signals:
            values[signal.signal_id] = (
                signal.all_supporting_job_ids,
                signal.supporting_job_ids,
                signal.supporting_evidence_ids,
                f"hiring_signal:{signal.signal_id}",
            )
        for label, concepts in (
            ("TECHNOLOGY", summary.observed_technologies),
            ("BUSINESS_UNIT", summary.observed_business_units),
            ("CAPABILITY", summary.observed_capabilities),
        ):
            for concept in concepts:
                reference = f"kg:{label.casefold()}:{concept.key}"
                support = (
                    concept.all_supporting_job_ids,
                    concept.supporting_job_ids,
                    concept.supporting_evidence_ids,
                    reference,
                )
                values[f"KG_{label}_{concept.key}"] = support
                values[reference] = support
        return values

    @staticmethod
    def _row(values, evidence_agent, support_index) -> IntelligenceOutlookRow:
        supporting = list(dict.fromkeys(item for value in values for item in value.supporting_evidence_ids))
        hiring_ids = [item for item in supporting if evidence_agent.get(item) == "hiring"]
        strategy_ids = [item for item in supporting if evidence_agent.get(item) == "strategy"]
        supports = [support_index[item] for item in hiring_ids if item in support_index]
        all_jobs = {job for job_ids, _, _, _ in supports for job in job_ids}
        jobs = sorted({job for _, job_ids, _, _ in supports for job in job_ids})
        evidence = sorted({item for _, _, evidence_ids, _ in supports for item in evidence_ids})
        all_evidence = list(dict.fromkeys([*supporting, *evidence]))
        concepts = sorted({reference for _, _, _, reference in supports if reference.startswith("kg:")})
        signals = sorted({item for item in hiring_ids if item in support_index and not item.startswith("KG_")})
        relevant = len(all_jobs) if supports else None
        limitations = [] if supports else ["No direct hiring evidence was linked to this opportunity."]
        horizons = {item.horizon_days: item.recommended_sales_action for item in values}
        strongest = max(values, key=lambda item: item.score)
        ranked_values = sorted(values, key=lambda item: (-item.score, item.title.casefold()))
        titles = list(dict.fromkeys(item.title.strip() for item in ranked_values if item.title.strip()))[:5]
        opportunity_name = next(
            (
                text.strip()
                for item in ranked_values
                for text in (item.title, item.recommended_solution, item.business_problem)
                if text.strip()
            ),
            "Opportunity not specified",
        )
        return IntelligenceOutlookRow(
            opportunity_theme=opportunity_name,
            supervisor_priority=strongest.client_priority,
            opportunity_titles=titles,
            relevant_hiring_jobs=relevant,
            supporting_evidence_count=len(all_evidence),
            supporting_job_ids=jobs[:10],
            supporting_evidence_ids=all_evidence[:10],
            strategy_evidence_ids=strategy_ids[:10],
            hiring_evidence_ids=hiring_ids[:10],
            hiring_signal_ids=signals[:10],
            kg_concept_references=concepts[:10],
            horizon_30=horizons.get(30),
            horizon_60=horizons.get(60),
            horizon_90=horizons.get(90),
            horizon_180=horizons.get(180),
            horizon_360=horizons.get(360),
            confidence=max(item.confidence for item in values),
            score=max(item.score for item in values),
            limitations=limitations,
        )
