from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SUPERVISOR_DIR = Path(__file__).resolve().parents[1]
if str(SUPERVISOR_DIR) not in sys.path:
    sys.path.insert(0, str(SUPERVISOR_DIR))

from supervisor import (
    ClientPriority,
    CompanyContext,
    CompanyScopeError,
    OpportunityDraft,
    SynthesisDraft,
    SupervisorRequest,
    extract_evidence,
    run_supervisor,
    validate_evidence,
)


class FakeResponses:
    def __init__(self, draft: SynthesisDraft):
        self.draft = draft
        self.call = None

    def parse(self, **kwargs):
        self.call = kwargs
        return SimpleNamespace(output_parsed=self.draft)


class FakeClient:
    def __init__(self, draft: SynthesisDraft):
        self.responses = FakeResponses(draft)


class IntegrationSupervisorTests(unittest.TestCase):
    def context(self):
        return CompanyContext(
            company_id="BARCLAYS",
            canonical_name="Barclays PLC",
            aliases=["Barclays"],
            allowed_subsidiaries=["Barclays Bank Delaware"],
            excluded_entities=["JPMorgan"],
        )

    def evidence(self, evidence_id="STRAT_1", **overrides):
        value = {
            "evidence_id": evidence_id,
            "company_id": "BARCLAYS",
            "topic": "Cloud modernization",
            "statement": "Barclays identified cloud modernization as a priority.",
            "source_date": "2026-08-01",
            "source_url": "https://example.test/source",
            "confidence": 0.8,
        }
        value.update(overrides)
        return value

    def request(self, **overrides):
        value = {
            "company_context": self.context(),
            "question": "Create an account growth report",
            "mode": "report",
            "strategy_output": {"company": "Barclays", "evidence": [self.evidence()]},
            "hiring_output": {"company_id": "BARCLAYS", "evidence": [
                self.evidence("HIRE_1", statement="Open cloud engineering role.", source_url="https://example.test/job")
            ]},
        }
        value.update(overrides)
        return SupervisorRequest(**value)

    def draft(self, **overrides):
        priority = ClientPriority(
            priority="Cloud modernization",
            explanation="Strategy and hiring evidence align.",
            supporting_evidence_ids=["STRAT_1", "HIRE_1"],
            confidence=0.8,
        )
        opportunity = OpportunityDraft(
            title="Cloud modernization discovery",
            client_priority="Cloud modernization",
            business_problem="Modernization planning",
            recommended_solution="Discovery and architecture assessment",
            supporting_evidence_ids=["STRAT_1", "HIRE_1"],
            why_now="Current strategy and hiring signals align.",
            recommended_sales_action="Schedule discovery with technology leaders.",
            consulting_fit=0.8,
            revenue_potential="medium",
        )
        value = {
            "executive_summary": "Cloud modernization is a supported priority.",
            "answer": "Begin with a discovery conversation.",
            "priorities": [priority],
            "opportunities": [opportunity],
        }
        value.update(overrides)
        return SynthesisDraft(**value)

    def test_report_has_an_evidence_backed_opportunity(self):
        result = run_supervisor(self.request(), client=FakeClient(self.draft()))
        self.assertEqual(len(result.opportunities), 1)
        self.assertEqual(result.opportunities[0].supporting_evidence_ids, ["STRAT_1", "HIRE_1"])

    def test_nested_company_contamination_is_rejected(self):
        request = self.request(strategy_output={"company": "Barclays", "evidence": [
            self.evidence(company_id="JPMorgan")
        ]})
        with self.assertRaises(CompanyScopeError):
            run_supervisor(request, client=FakeClient(self.draft()))

    def test_alias_and_allowed_subsidiary_are_accepted(self):
        request = self.request(strategy_output={"company": "Barclays Bank Delaware", "evidence": [
            self.evidence(company_id="Barclays")
        ]})
        result = run_supervisor(request, client=FakeClient(self.draft()))
        self.assertEqual(result.company_id, "BARCLAYS")

    def test_duplicate_evidence_is_removed(self):
        duplicate = self.evidence("STRAT_2")
        extracted = extract_evidence({"evidence": [self.evidence(), duplicate]}, "strategy")
        accepted, rejected = validate_evidence(extracted, self.context())
        self.assertEqual(len(accepted), 1)
        self.assertIn("duplicate", rejected[0])

    def test_filing_sourced_evidence_is_classified_as_filing(self):
        filing = self.evidence("STRAT_FILING", source_type="quarterly_report")
        news = self.evidence("STRAT_NEWS", source_type="news")
        extracted = extract_evidence({"evidence": [filing, news]}, "strategy")
        by_id = {item.evidence_id: item for item in extracted}
        self.assertEqual(by_id["STRAT_FILING"].evidence_type, "filing")
        self.assertNotEqual(by_id["STRAT_NEWS"].evidence_type, "filing")

    def test_invented_evidence_removes_priority_and_opportunity(self):
        bad_priority = ClientPriority(
            priority="Unsupported",
            explanation="Unsupported model claim",
            supporting_evidence_ids=["MADE_UP"],
            confidence=0.9,
        )
        bad_opportunity = OpportunityDraft(
            title="Unsupported opportunity",
            client_priority="Unsupported",
            business_problem="Unknown",
            recommended_solution="Unknown",
            supporting_evidence_ids=["MADE_UP"],
            why_now="Unknown",
            recommended_sales_action="Unknown",
        )
        result = run_supervisor(
            self.request(),
            client=FakeClient(self.draft(priorities=[bad_priority], opportunities=[bad_opportunity])),
        )
        self.assertFalse(result.client_priorities)
        self.assertFalse(result.opportunities)
        self.assertTrue(result.limitations)

    def test_qa_mode_does_not_return_opportunities(self):
        result = run_supervisor(
            self.request(mode="qa", question="Why is cloud modernization a priority?"),
            client=FakeClient(self.draft()),
        )
        self.assertEqual(result.mode, "qa")
        self.assertFalse(result.opportunities)

    def test_empty_outputs_do_not_call_model(self):
        result = run_supervisor(self.request(strategy_output={}, hiring_output={}))
        self.assertFalse(result.evidence_assessment.sufficient)
        self.assertEqual(result.opportunities, [])


if __name__ == "__main__":
    unittest.main()
