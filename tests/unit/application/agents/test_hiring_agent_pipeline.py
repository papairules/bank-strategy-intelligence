import csv
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.application.agents.hiring_agent.pipeline import (
    CompanyContext,
    FetchResult,
    HiringAgentOutput,
    HiringAgentRequest,
    JobClassification,
    JobClassificationBatch,
    JobPageParser,
    load_jobs,
    load_jobs_detailed,
    repair_text,
    run_hiring_agent,
    run_hiring_agent_request,
    validate_fetched_company,
)


HEADERS = [
    "company", "source_job_id", "title", "role_family", "city", "state",
    "country", "workplace_type", "employment_type", "first_seen_at",
    "source_posted_at", "posting_url",
]


class FakeFetcher:
    def fetch(self, job):
        return FetchResult(
            status="completed",
            source_url=job.posting_url,
            final_url=job.posting_url,
            http_status=200,
            text="A sufficiently long job description for testing data, cloud, and Python skills. " * 3,
            structured_data={"title": job.title, "datePosted": "2026-08-01"},
        )


class FakeResponses:
    def parse(self, **kwargs):
        return SimpleNamespace(
            output_parsed=JobClassificationBatch(
                classifications=[
                    JobClassification(source_job_id="INVENTED", capability="AI", confidence=1.0),
                ]
            )
        )


class FakeClient:
    responses = FakeResponses()


def write_csv(path: Path, rows: list[list[str]], headers: list[str] = HEADERS) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(rows)


def barclays_context() -> CompanyContext:
    return CompanyContext(
        company_id="BARCLAYS",
        canonical_name="Barclays PLC",
        aliases=["BARCLAYS", "Barclays"],
        allowed_subsidiaries=["Barclays Bank"],
        excluded_entities=["JPMorgan"],
    )


def barclays_rows() -> list[list[str]]:
    return [
        ["Barclays", "B1", "Director of AI", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-01", "2026-08-01", "https://example.com/B1"],
        ["Barclays Bank", "B2", "Cloud Engineer", "Technology", "London", "", "UK", "hybrid", "Full time", "2026-08-02", "2026-08-02", "https://example.com/B2"],
        ["JPMorgan", "J1", "Data Engineer", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-02", "2026-08-02", "https://example.com/J1"],
    ]


def test_filters_company_and_builds_offline_output(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(
        path,
        [
            ["BARCLAYS", "B1", "Director of AI Platform", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-01", "2026-07-30", "https://example.com/B1"],
            ["BARCLAYS", "B2", "Senior Data Engineer", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-02", "2026-08-01", "https://example.com/B2"],
            ["OTHER", "O1", "Risk Analyst", "Risk", "Boston", "MA", "US", "onsite", "Full time", "2026-08-02", "2026-08-01", "https://example.com/O1"],
        ],
    )
    result = run_hiring_agent(
        company="Barclays",
        input_paths=[path],
        cache_dir=tmp_path / "cache",
        skip_url_enrichment=True,
        use_llm=False,
    )
    assert result.total_input_jobs == 2
    assert result.unique_jobs == 2
    assert result.hiring_signals
    assert all(item.company_id == "BARCLAYS" for item in result.evidence)
    assert all(signal.direction == "concentration" for signal in result.hiring_signals)


def test_deduplicates_jobs(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(
        path,
        [
            ["BARCLAYS", "B1", "Director of AI Platform", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-01", "2026-07-30", "https://example.com/B1"],
            ["BARCLAYS", "B2", "Senior Data Engineer", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-02", "2026-08-01", "https://example.com/B2"],
        ],
    )
    jobs, _ = load_jobs([path, path], "BARCLAYS")
    assert len(jobs) == 2


def test_does_not_claim_growth_from_snapshot(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(
        path,
        [
            ["BARCLAYS", "B1", "Director of AI Platform", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-01", "2026-07-30", "https://example.com/B1"],
            ["BARCLAYS", "B2", "Senior Data Engineer", "Technology", "New York", "NY", "US", "hybrid", "Full time", "2026-08-02", "2026-08-01", "https://example.com/B2"],
        ],
    )
    result = run_hiring_agent(
        company="BARCLAYS",
        input_paths=[path],
        cache_dir=tmp_path / "cache",
        skip_url_enrichment=True,
        use_llm=False,
    )
    assert "growth" not in {signal.direction for signal in result.hiring_signals}
    assert any("active-job snapshot" in warning for warning in result.warnings)


def test_repairs_common_mojibake():
    assert repair_text("Director â€“ Compliance") == "Director – Compliance"


def test_company_aliases_and_subsidiaries_are_accepted(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(path, barclays_rows())
    jobs, diagnostics = load_jobs_detailed([path], barclays_context())
    assert {job.source_job_id for job in jobs} == {"B1", "B2"}
    assert diagnostics.other_company_rows == 1


def test_missing_required_column_is_rejected(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(path, [["Barclays", "B1", "AI Engineer"]], headers=["company", "source_job_id", "title"])
    with pytest.raises(ValueError, match="missing required columns"):
        load_jobs_detailed([path], barclays_context())


def test_summary_output_omits_full_jobs(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(path, barclays_rows())
    request = HiringAgentRequest(
        company_context=barclays_context(),
        input_files=[path],
        cache_directory=tmp_path / "cache",
        use_llm=False,
        output_level="summary",
    )
    result = run_hiring_agent_request(request, fetcher=FakeFetcher())
    assert result.schema_version == "1.0"
    assert result.jobs == []
    assert result.enriched_jobs == 2
    assert result.evidence


def test_full_output_keeps_jobs_and_provenance(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(path, barclays_rows()[:1])
    request = HiringAgentRequest(
        company_context=barclays_context(),
        input_files=[path],
        cache_directory=tmp_path / "cache",
        use_llm=False,
        output_level="full",
    )
    result = run_hiring_agent_request(request, fetcher=FakeFetcher())
    assert len(result.jobs) == 1
    assert result.jobs[0].classification_source == "heuristic"
    assert result.evidence[0].source_job_id == result.jobs[0].source_job_id


def test_historical_snapshot_enables_direction(tmp_path: Path):
    current = tmp_path / "current.csv"
    historical = tmp_path / "historical.csv"
    current_rows = barclays_rows()[:2]
    write_csv(current, current_rows)
    write_csv(historical, [current_rows[0]])
    request = HiringAgentRequest(
        company_context=barclays_context(),
        input_files=[current],
        historical_input_files=[historical],
        cache_directory=tmp_path / "cache",
        enrich_urls=False,
        use_llm=False,
    )
    result = run_hiring_agent_request(request)
    assert all(signal.previous_job_count is not None for signal in result.hiring_signals)
    assert {signal.direction for signal in result.hiring_signals} <= {"growth", "decline", "stable"}


def test_jobposting_json_ld_is_extracted():
    parser = JobPageParser()
    parser.feed(
        '<html><script type="application/ld+json">'
        '{"@type":"JobPosting","title":"AI Engineer","datePosted":"2026-08-01",'
        '"description":"Build AI systems"}</script><body>Visible page</body></html>'
    )
    data = parser.job_posting()
    assert data["title"] == "AI Engineer"
    assert data["datePosted"] == "2026-08-01"


def test_explicit_other_company_page_is_rejected():
    fetched = {
        "B1": FetchResult(
            status="completed",
            source_url="https://example.com/B1",
            text="Job description",
            structured_data={"hiringOrganization": {"name": "JPMorgan"}},
        )
    }
    warnings = validate_fetched_company(fetched, barclays_context())
    assert fetched["B1"].status == "failed"
    assert fetched["B1"].text is None
    assert warnings


def test_invented_llm_job_id_is_ignored(tmp_path: Path):
    path = tmp_path / "jobs.csv"
    write_csv(path, barclays_rows()[:1])
    request = HiringAgentRequest(
        company_context=barclays_context(),
        input_files=[path],
        cache_directory=tmp_path / "cache",
        use_llm=True,
        llm_retries=0,
        output_level="full",
    )
    result = run_hiring_agent_request(request, client=FakeClient(), fetcher=FakeFetcher())
    assert result.jobs[0].classification_source == "heuristic"
    assert any("omitted" in warning for warning in result.warnings)


def test_unknown_supporting_job_id_fails_output_validation():
    payload = {
        "schema_version": "1.0",
        "company_id": "BARCLAYS",
        "company_name": "Barclays PLC",
        "generated_at": "2026-08-21T00:00:00+00:00",
        "output_level": "summary",
        "source_files": [],
        "diagnostics": {},
        "total_input_jobs": 0,
        "unique_jobs": 0,
        "enriched_jobs": 0,
        "failed_enrichments": 0,
        "hiring_signals": [{
            "company_id": "BARCLAYS", "capability": "Data and AI",
            "direction": "concentration", "strength": 0.5, "job_count": 1,
            "senior_role_count": 0, "supporting_job_ids": ["UNKNOWN"],
            "evidence_date": "2026-08-21", "analysis_period": "snapshot",
            "confidence": 0.5, "confidence_breakdown": {},
        }],
        "evidence": [],
        "jobs": [],
        "warnings": [],
    }
    with pytest.raises(ValidationError, match="unknown job IDs"):
        HiringAgentOutput.model_validate(payload)
