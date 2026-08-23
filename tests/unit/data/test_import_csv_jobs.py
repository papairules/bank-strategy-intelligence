import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "data" / "import_csv_jobs.py"

_spec = importlib.util.spec_from_file_location("import_csv_jobs", MODULE_PATH)
import_csv_jobs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(import_csv_jobs)


def base_row(**overrides):
    row = {
        "company": "WELLS_FARGO",
        "source_job_id": "SRC-1",
        "title": "Platform Engineer",
        "role_family": "Cloud and Infrastructure",
        "city": "Charlotte",
        "state": "NC",
        "country": "US",
        "employment_type": "Full time",
        "description_text": "Build platform services.",
        "source_posted_at": "2026-08-01",
        "posting_url": "https://jobs.example.test/1",
    }
    row.update(overrides)
    return row


def test_role_family_becomes_capability_classification():
    job = import_csv_jobs.build_collected_job(base_row())

    assert job is not None
    assert job.posting.capability_classifications == ["Cloud and Infrastructure"]


def test_blank_role_family_yields_no_capability_classification():
    job = import_csv_jobs.build_collected_job(base_row(role_family=""))

    assert job is not None
    assert job.posting.capability_classifications == []


def test_missing_role_family_column_yields_no_capability_classification():
    row = base_row()
    del row["role_family"]

    job = import_csv_jobs.build_collected_job(row)

    assert job is not None
    assert job.posting.capability_classifications == []


def test_technologies_are_keyword_matched_from_title_and_description():
    job = import_csv_jobs.build_collected_job(
        base_row(
            title="Senior Python Developer",
            description_text="Build services using Python, Kubernetes, and Kafka.",
        )
    )

    assert job is not None
    assert job.posting.technologies == ["Kafka", "Kubernetes", "Python"]


def test_no_technologies_in_plain_description_yields_empty_list():
    job = import_csv_jobs.build_collected_job(base_row())

    assert job is not None
    assert job.posting.technologies == []


def test_recommended_jobs_widget_is_stripped_before_storage_and_technology_matching():
    row = base_row(
        title="Investment Banking Associate",
        description_text=(
            "Assist clients with mergers and acquisitions advisory services.\n"
            "Explore More Jobs\n"
            "Technical Lead (Core Java) - Assistant Vice President\n"
            "Save for Later"
        ),
    )

    job = import_csv_jobs.build_collected_job(row)

    assert job is not None
    assert "Explore More Jobs" not in job.posting.description
    assert "Java" not in job.posting.description
    assert job.posting.technologies == []


def test_technologies_also_match_qualifications_and_responsibilities_columns():
    job = import_csv_jobs.build_collected_job(
        base_row(
            qualifications_text="Experience with Snowflake required.",
            responsibilities_text="Maintain Tableau dashboards.",
        )
    )

    assert job is not None
    assert job.posting.technologies == ["Snowflake", "Tableau"]
