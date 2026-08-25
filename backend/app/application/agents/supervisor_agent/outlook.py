from pydantic import BaseModel, ConfigDict, Field

from .supervisor import Opportunity, SupervisorResponse, map_signal_strength


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


class LOBOpportunityRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    line_of_business: str
    emerging_ai_theme: str
    likely_use_cases: list[str] = Field(default_factory=list)
    signal_strength: str
    relevant_hiring_jobs: int | None = Field(default=None, ge=0)
    narrative: str = Field(max_length=900)
    supporting_reference_ids: list[str] = Field(default_factory=list)


class LOBOpportunityMapper:
    def map(self, normalized, supervisor: SupervisorResponse) -> list[LOBOpportunityRow]:
        support_index = _hiring_support_index(normalized)
        grouped: dict[str, list[Opportunity]] = {}
        for opportunity in supervisor.opportunities:
            lob = (opportunity.business_unit or "Unspecified").strip() or "Unspecified"
            grouped.setdefault(lob, []).append(opportunity)
        ranked = sorted(
            grouped.items(),
            key=lambda pair: (-max(item.score for item in pair[1]), pair[0].casefold()),
        )
        return [self._row(lob, items, support_index) for lob, items in ranked]

    @staticmethod
    def _row(line_of_business: str, items: list[Opportunity], support_index) -> LOBOpportunityRow:
        strongest = max(items, key=lambda item: item.score)
        use_cases = list(dict.fromkeys(case.strip() for item in items for case in item.likely_use_cases if case.strip()))[:6]
        supporting = list(dict.fromkeys(item for value in items for item in value.supporting_evidence_ids))
        supports = [support_index[item] for item in supporting if item in support_index]
        jobs = {job for _, job_ids, _, _ in supports for job in job_ids}
        narrative = (strongest.narrative or strongest.why_now or "").strip()
        if len(narrative) > 900:
            narrative = narrative[:897].rstrip() + "..."
        if not narrative:
            narrative = "No additional detail was provided for this opportunity."
        return LOBOpportunityRow(
            line_of_business=line_of_business,
            emerging_ai_theme=(strongest.emerging_ai_theme or strongest.client_priority).strip(),
            likely_use_cases=use_cases,
            signal_strength=map_signal_strength(strongest.score),
            relevant_hiring_jobs=len(jobs) if supports else None,
            narrative=narrative,
            supporting_reference_ids=supporting[:10],
        )
