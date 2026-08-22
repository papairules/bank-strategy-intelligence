import json
from types import SimpleNamespace

import pytest

from backend.app.application.agents.supervisor_agent import (
    IntelligenceOutlookRow,
    ReportFinding,
    ReportQAError,
    ReportQAErrorCode,
    ReportQAService,
    ReportQuestionContext,
    ReportQuestionRequest,
    ReportSupportReference,
)


class FakeResponses:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.output, Exception):
            raise self.output
        if self.output == "schema_instance":
            return SimpleNamespace(output_parsed=kwargs["text_format"](
                answer="Grounded answer.",
                supporting_reference_ids=["outlook:1"],
                evidence_sufficient=True,
                limitations=[],
            ))
        return SimpleNamespace(output_parsed=self.output)


class FakeClient:
    def __init__(self, output):
        self.responses = FakeResponses(output)


def context():
    return ReportQuestionContext(
        organization="Wells Fargo",
        total_hiring_jobs=1610,
        executive_summary="Evidence indicates modernization.",
        intelligence_outlook_rows=[
            IntelligenceOutlookRow(
                opportunity_theme="Operating-model modernization",
                supervisor_priority="Modernization",
                relevant_hiring_jobs=1203,
                supporting_evidence_count=2,
                supporting_job_ids=["WF-JOB-1"],
                supporting_evidence_ids=["EV-1"],
                strategy_evidence_ids=["STRATEGY-1"],
                hiring_evidence_ids=["EV-1"],
                horizon_90="Validate the modernization roadmap.",
                confidence=.8,
                score=80,
            )
        ],
        strategic_priorities=[
            ReportFinding(title="Modernization", narrative="Modernization is a priority.")
        ],
        cross_domain_alignment=[
            ReportFinding(title="Alignment", narrative="Strategy and hiring appear aligned.")
        ],
        evidence_traceability=[
            ReportSupportReference(
                reference_id="STRATEGY-1",
                domain="strategy",
                source_url="https://wellsfargo.com/report",
            ),
            ReportSupportReference(reference_id="EV-1", domain="hiring_kg"),
        ],
        limitations=["Observed alignment does not prove causation."],
    )


def request(question="What should we prioritize in the next 90 days?"):
    return ReportQuestionRequest(
        organization="Wells Fargo", question=question, report=context()
    )


def service(output):
    client = FakeClient(output)
    return ReportQAService(
        client_factory=lambda: client,
        model="test-model",
        enabled=True,
    ), client


def test_answer_uses_compact_existing_report_context_and_preserves_references():
    qa, client = service({
        "answer": "Prioritize validating the modernization roadmap in the next 90 days.",
        "supporting_reference_ids": ["outlook:1", "STRATEGY-1"],
        "evidence_sufficient": True,
        "limitations": ["This is an evidence-backed inference."],
    })
    result = qa.answer(request())

    assert result.organization == "Wells Fargo"
    assert result.evidence_sufficient is True
    assert result.supporting_references[0].hiring_job_count == 1203
    assert result.supporting_references[1].source_url == "https://wellsfargo.com/report"
    call = client.responses.calls[0]
    assert call["model"] == "test-model"
    assert "tools" not in call
    reference_schema = call["text_format"].model_json_schema()["properties"]["supporting_reference_ids"]["items"]
    assert set(reference_schema["enum"]) == {"outlook:1", "STRATEGY-1", "EV-1"}
    payload = json.loads(call["input"])
    assert payload["report"]["intelligence_outlook_rows"][0]["horizon_90"] == "Validate the modernization roadmap."
    assert payload["report"]["intelligence_outlook_rows"][0]["relevant_hiring_jobs"] == 1203
    assert "supporting_job_ids" not in payload["report"]["intelligence_outlook_rows"][0]


def test_insufficient_evidence_is_allowed_without_references():
    qa, _ = service({
        "answer": "The current report does not contain enough evidence to answer that question.",
        "supporting_reference_ids": [],
        "evidence_sufficient": False,
        "limitations": ["No report evidence addresses exact budgets."],
    })
    result = qa.answer(request("What exact budget will Wells Fargo approve?"))

    assert result.evidence_sufficient is False
    assert result.supporting_references == []


@pytest.mark.parametrize(
    "question",
    ["What are the top opportunities?", "What does Wells Fargo hiring tell us?"],
)
def test_top_opportunity_and_hiring_questions_use_existing_outlook_counts(question):
    qa, client = service({
        "answer": "The report supports operating-model modernization.",
        "supporting_reference_ids": ["outlook:1"],
        "evidence_sufficient": True,
        "limitations": [],
    })
    result = qa.answer(request(question))

    assert result.supporting_references[0].hiring_job_count == 1203
    payload = json.loads(client.responses.calls[0]["input"])
    assert payload["report"]["intelligence_outlook_rows"][0]["score"] == 80


def test_cross_company_question_is_rejected_before_provider_call():
    qa, client = service({})
    with pytest.raises(ReportQAError) as caught:
        qa.answer(request("What are Goldman Sachs's top opportunities?"))

    assert caught.value.code == ReportQAErrorCode.ORGANIZATION_SCOPE_MISMATCH
    assert client.responses.calls == []


def test_invented_reference_is_rejected():
    qa, _ = service({
        "answer": "Unsupported answer.",
        "supporting_reference_ids": ["invented-source"],
        "evidence_sufficient": True,
        "limitations": [],
    })
    with pytest.raises(ReportQAError) as caught:
        qa.answer(request())
    assert caught.value.code == ReportQAErrorCode.MALFORMED_PROVIDER_OUTPUT


def test_provider_failure_is_secret_safe():
    qa, _ = service(RuntimeError("sdk failure containing internal details"))
    with pytest.raises(ReportQAError) as caught:
        qa.answer(request())
    assert caught.value.code == ReportQAErrorCode.PROVIDER_FAILURE
    assert str(caught.value) == "Report Q&A is temporarily unavailable."


def test_constrained_provider_model_instance_is_deserialized():
    qa, _ = service("schema_instance")
    result = qa.answer(request())
    assert result.evidence_sufficient is True
    assert result.supporting_references[0].reference_id == "outlook:1"
