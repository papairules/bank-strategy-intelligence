from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.application.agents.supervisor_agent import (
    CompactHiringKGSummary,
    DeterministicIntelligenceOutlookMapper,
    EvidenceAssessment,
    EvidenceReference,
    HorizonSection,
    ObservedHiringSignalSupport,
    ObservedKGConcept,
    Opportunity,
    SupervisorResponse,
)


def opportunity(*, title, priority, horizon, evidence, score=80):
    return Opportunity(
        title=title,
        client_priority=priority,
        business_problem="problem",
        recommended_solution="solution",
        supporting_evidence_ids=evidence,
        why_now="why now",
        recommended_sales_action=f"Act by day {horizon}",
        confidence=.8,
        score=score,
        revenue_potential="high",
        horizon_days=horizon,
        horizon_reason="evidence",
    )


def response(opportunities):
    horizons = []
    for horizon in (30, 60, 90, 180, 360):
        selected = [item for item in opportunities if item.horizon_days == horizon]
        horizons.append(HorizonSection(horizon_days=horizon, meaning="act", opportunities=selected))
    evidence_ids = {item for value in opportunities for item in value.supporting_evidence_ids}
    return SupervisorResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        company_id="WELLS_FARGO",
        company_name="Wells Fargo",
        question="report",
        mode="report",
        executive_summary="summary",
        evidence_assessment=EvidenceAssessment(sufficient=True, overall_confidence=.8),
        horizons=horizons,
        evidence=[
            EvidenceReference(
                evidence_id=item,
                agent="strategy" if item.startswith("STRATEGY") else "hiring",
                statement="evidence",
            )
            for item in evidence_ids
        ],
        limitations=[],
        answer="answer",
    )


def normalized():
    summary = CompactHiringKGSummary(
        organization="Wells Fargo",
        node_count=10,
        edge_count=10,
        enriched_jobs_used=4,
        observed_technologies=[
            ObservedKGConcept(
                key="cloud",
                name="Cloud",
                job_count=3,
                supporting_job_ids=["J1", "J2", "J3"],
                supporting_evidence_ids=["E1", "E2"],
                all_supporting_job_ids=["J1", "J2", "J3"],
            )
        ],
        observed_hiring_signals=[
            ObservedHiringSignalSupport(
                signal_id="SIGNAL-A",
                job_count=3,
                supporting_job_ids=["J2", "J3", "J4"],
                supporting_evidence_ids=["E2", "E3"],
                all_supporting_job_ids=["J2", "J3", "J4"],
            )
        ],
    )
    return SimpleNamespace(hiring=SimpleNamespace(kg_summary=summary))


def test_groups_same_theme_across_horizons_and_deduplicates_exact_job_union():
    values = [
        opportunity(
            title="Cloud roadmap",
            priority="Highest",
            horizon=30,
            evidence=["STRATEGY-1", "KG_TECHNOLOGY_cloud"],
        ),
        opportunity(
            title="Delivery mobilization",
            priority="Highest",
            horizon=90,
            evidence=["SIGNAL-A"],
            score=85,
        ),
    ]
    rows = DeterministicIntelligenceOutlookMapper().map(normalized(), response(values))

    assert len(rows) == 1
    assert rows[0].opportunity_theme == "Delivery mobilization"
    assert rows[0].supervisor_priority == "Highest"
    assert rows[0].opportunity_titles == ["Delivery mobilization", "Cloud roadmap"]
    assert rows[0].relevant_hiring_jobs == 4
    assert rows[0].supporting_evidence_count == 6
    assert rows[0].supporting_job_ids == ["J1", "J2", "J3", "J4"]
    assert rows[0].strategy_evidence_ids == ["STRATEGY-1"]
    assert rows[0].hiring_signal_ids == ["SIGNAL-A"]
    assert rows[0].kg_concept_references == ["kg:technology:cloud"]
    assert rows[0].horizon_30 == "Act by day 30"
    assert rows[0].horizon_90 == "Act by day 90"
    assert rows[0].limitations == []


def test_matching_is_exact_and_unsupported_theme_has_explicit_fallback():
    value = opportunity(
        title="No mapped support",
        priority="Operating model",
        horizon=60,
        evidence=["STRATEGY-1", "KG_TECHNOLOGY_cloud_native"],
    )
    row = DeterministicIntelligenceOutlookMapper().map(normalized(), response([value]))[0]

    assert row.relevant_hiring_jobs is None
    assert row.supporting_job_ids == []
    assert row.kg_concept_references == []
    assert row.limitations == ["No direct hiring evidence was linked to this opportunity."]


def test_output_is_limited_to_five_strongest_supervisor_themes():
    values = [
        opportunity(
            title=f"Opportunity {index}",
            priority=f"Priority {index}",
            horizon=30,
            evidence=["STRATEGY-1"],
            score=50 + index,
        )
        for index in range(6)
    ]
    rows = DeterministicIntelligenceOutlookMapper().map(normalized(), response(values))

    assert len(rows) == 5
    assert [row.score for row in rows] == [55, 54, 53, 52, 51]


def test_missing_descriptive_text_does_not_expose_priority_as_opportunity():
    value = opportunity(
        title="",
        priority="Highest",
        horizon=30,
        evidence=["STRATEGY-1"],
    )
    value.recommended_solution = ""
    value.business_problem = ""

    row = DeterministicIntelligenceOutlookMapper().map(normalized(), response([value]))[0]

    assert row.opportunity_theme == "Opportunity not specified"
    assert row.supervisor_priority == "Highest"
    assert row.opportunity_titles == []


def test_private_full_job_support_is_not_serialized():
    payload = normalized().hiring.kg_summary.model_dump(mode="json")

    assert "all_supporting_job_ids" not in payload["observed_technologies"][0]
    assert "all_supporting_job_ids" not in payload["observed_hiring_signals"][0]
