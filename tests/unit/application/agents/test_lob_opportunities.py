from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.application.agents.supervisor_agent import (
    CompactHiringKGSummary,
    EvidenceAssessment,
    EvidenceReference,
    LOBOpportunityMapper,
    ObservedHiringSignalSupport,
    ObservedKGConcept,
    Opportunity,
    SupervisorResponse,
)


def opportunity(
    *,
    title,
    business_unit,
    priority,
    evidence,
    score=80,
    emerging_ai_theme=None,
    likely_use_cases=None,
    narrative=None,
    why_now="why now",
):
    return Opportunity(
        title=title,
        business_unit=business_unit,
        client_priority=priority,
        business_problem="problem",
        recommended_solution="solution",
        supporting_evidence_ids=evidence,
        why_now=why_now,
        recommended_sales_action="act now",
        confidence=.8,
        score=score,
        revenue_potential="high",
        emerging_ai_theme=emerging_ai_theme,
        likely_use_cases=likely_use_cases or [],
        narrative=narrative,
    )


def response(opportunities):
    evidence_ids = {item for value in opportunities for item in value.supporting_evidence_ids}
    return SupervisorResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        company_id="WELLS_FARGO",
        company_name="Wells Fargo",
        question="report",
        mode="report",
        executive_summary="summary",
        evidence_assessment=EvidenceAssessment(sufficient=True, overall_confidence=.8),
        opportunities=opportunities,
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


def test_groups_same_line_of_business_and_deduplicates_exact_job_union():
    values = [
        opportunity(
            title="Cloud roadmap",
            business_unit="Commercial Banking",
            priority="Highest",
            evidence=["STRATEGY-1", "KG_TECHNOLOGY_cloud"],
            emerging_ai_theme="Cloud modernization",
        ),
        opportunity(
            title="Delivery mobilization",
            business_unit="Commercial Banking",
            priority="Highest",
            evidence=["SIGNAL-A"],
            score=85,
            emerging_ai_theme="Delivery acceleration",
        ),
    ]
    rows = LOBOpportunityMapper().map(normalized(), response(values))

    assert len(rows) == 1
    assert rows[0].line_of_business == "Commercial Banking"
    # The strongest-scoring opportunity's theme wins the row.
    assert rows[0].emerging_ai_theme == "Delivery acceleration"
    assert rows[0].relevant_hiring_jobs == 4
    assert set(rows[0].supporting_reference_ids) == {"STRATEGY-1", "KG_TECHNOLOGY_cloud", "SIGNAL-A"}


def test_distinct_lines_of_business_are_not_merged_and_tie_break_alphabetically():
    values = [
        opportunity(title="A", business_unit="Wealth Management", priority="P1", evidence=["STRATEGY-1"]),
        opportunity(title="B", business_unit="Commercial Banking", priority="P2", evidence=["STRATEGY-1"]),
        opportunity(title="C", business_unit="Technology", priority="P3", evidence=["STRATEGY-1"]),
    ]
    rows = LOBOpportunityMapper().map(normalized(), response(values))

    # All three share the same default score, so equal-strength rows fall back to alphabetical order.
    assert [row.line_of_business for row in rows] == ["Commercial Banking", "Technology", "Wealth Management"]


def test_rows_are_ordered_by_signal_strength_high_to_low():
    values = [
        opportunity(title="A", business_unit="Low LOB", priority="P", evidence=["STRATEGY-1"], score=20),
        opportunity(title="B", business_unit="High LOB", priority="P", evidence=["STRATEGY-1"], score=90),
        opportunity(title="C", business_unit="Medium LOB", priority="P", evidence=["STRATEGY-1"], score=50),
    ]
    rows = LOBOpportunityMapper().map(normalized(), response(values))

    assert [row.line_of_business for row in rows] == ["High LOB", "Medium LOB", "Low LOB"]
    assert [row.signal_strength for row in rows] == ["Very High", "Medium", "Low"]


def test_missing_business_unit_falls_back_to_unspecified():
    value = opportunity(title="A", business_unit=None, priority="P1", evidence=["STRATEGY-1"])
    rows = LOBOpportunityMapper().map(normalized(), response([value]))

    assert rows[0].line_of_business == "Unspecified"


def test_matching_is_exact_and_unsupported_theme_reports_no_hiring_jobs():
    value = opportunity(
        title="No mapped support",
        business_unit="Risk",
        priority="Operating model",
        evidence=["STRATEGY-1", "KG_TECHNOLOGY_cloud_native"],
    )
    row = LOBOpportunityMapper().map(normalized(), response([value]))[0]

    assert row.relevant_hiring_jobs is None


def test_emerging_ai_theme_falls_back_to_client_priority_when_unset():
    value = opportunity(
        title="A", business_unit="Risk", priority="Fraud modernization",
        evidence=["STRATEGY-1"], emerging_ai_theme=None,
    )
    row = LOBOpportunityMapper().map(normalized(), response([value]))[0]

    assert row.emerging_ai_theme == "Fraud modernization"


def test_narrative_falls_back_to_why_now_then_default_and_is_truncated():
    with_narrative = opportunity(title="A", business_unit="Risk", priority="P", evidence=["STRATEGY-1"], narrative="Grounded summary.")
    assert LOBOpportunityMapper().map(normalized(), response([with_narrative]))[0].narrative == "Grounded summary."

    without_narrative = opportunity(title="A", business_unit="Risk", priority="P", evidence=["STRATEGY-1"], narrative=None)
    row = LOBOpportunityMapper().map(normalized(), response([without_narrative]))[0]
    assert row.narrative == "why now"

    long_narrative = opportunity(title="A", business_unit="Risk", priority="P", evidence=["STRATEGY-1"], narrative="x" * 1000)
    row = LOBOpportunityMapper().map(normalized(), response([long_narrative]))[0]
    assert len(row.narrative) == 900
    assert row.narrative.endswith("...")

    nothing_at_all = opportunity(title="A", business_unit="Risk", priority="P", evidence=["STRATEGY-1"], narrative=None, why_now="")
    row = LOBOpportunityMapper().map(normalized(), response([nothing_at_all]))[0]
    assert row.narrative == "No additional detail was provided for this opportunity."


def test_signal_strength_reflects_score_thresholds():
    values = [
        opportunity(title="Very high", business_unit="A", priority="P", evidence=["STRATEGY-1"], score=80),
        opportunity(title="High", business_unit="B", priority="P", evidence=["STRATEGY-1"], score=65),
        opportunity(title="Medium", business_unit="C", priority="P", evidence=["STRATEGY-1"], score=45),
        opportunity(title="Low", business_unit="D", priority="P", evidence=["STRATEGY-1"], score=10),
    ]
    rows = {row.line_of_business: row.signal_strength for row in LOBOpportunityMapper().map(normalized(), response(values))}

    assert rows == {"A": "Very High", "B": "High", "C": "Medium", "D": "Low"}


def test_private_full_job_support_is_not_serialized():
    payload = normalized().hiring.kg_summary.model_dump(mode="json")

    assert "all_supporting_job_ids" not in payload["observed_technologies"][0]
    assert "all_supporting_job_ids" not in payload["observed_hiring_signals"][0]
