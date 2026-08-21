# Bank Strategy Intelligence

Bank Strategy Intelligence is a backend platform for researching banking organizations and producing traceable intelligence signals. The V1 vertical implements Hiring Intelligence for public Wells Fargo job postings, with deterministic collection, normalization, persistence, run auditing, scheduling foundations, and a read-only API.

## V1 Scope

The current implementation provides:

- Public Wells Fargo Workday job search and detail collection.
- Source-neutral pagination, record limits, cursor protection, and partial-failure handling.
- Deterministic Wells Fargo normalization into `JobPosting` and `Evidence` domain models.
- SQLite persistence with idempotent job upserts.
- `CollectionRun` audit records for completed, partial, and failed runs.
- A source-neutral execution service and in-memory interval scheduler.
- A versioned, read-only FastAPI API for persisted jobs, evidence, and runs.

V1 does not include enrichment, AI/LLM processing, strategy analysis, multi-agent orchestration, authentication, a frontend, or additional banks.

## Architecture

```text
Public Wells Fargo Workday CXS endpoints
    -> WellsFargoSourceAdapter
    -> PaginatedJobCollector
    -> WellsFargoJobNormalizer
    -> JobPosting + Evidence
    -> HiringCollectionExecutionService
    -> SQLite persistence
    -> CollectionRun observability
    -> HiringCollectionScheduler
    -> FastAPI read API
```

The core boundaries are source-neutral. Wells Fargo and Workday-specific parsing is isolated under infrastructure, while domain models, execution, scheduling, and persistence protocols do not depend on that source.

## Package Structure

```text
backend/app/
├── api/                         # FastAPI dependencies and versioned read routes
│   └── v1/hiring/
├── application/hiring/          # Collection contracts, execution, queries, auditing, scheduling
├── domain/hiring/                # JobPosting and hiring enums
├── domain/intelligence/          # Evidence and intelligence signal contracts
├── infrastructure/collectors/    # Generic collector plus source adapters/normalizers
│   └── hiring/sources/wells_fargo/
├── infrastructure/composition/   # Wells Fargo execution and scheduler wiring
├── infrastructure/persistence/   # SQLite repositories and schema
├── config.py                     # Environment-backed settings
└── main.py                       # FastAPI application entry point

tests/
├── api/
└── unit/
```

## Requirements

- Python 3.13 or newer
- `pip`

SQLite is provided by Python's standard library. No external database service is required for local V1 use.

## Setup

```bash
git clone <repository-url>
cd bank-strategy-intelligence
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Run Tests

```bash
pytest
```

The suite is fully offline. Wells Fargo HTTP behavior is tested with synthetic fixtures and `httpx.MockTransport`; tests do not crawl or contact Workday.

## Run FastAPI Locally

```bash
uvicorn backend.app.main:app --reload
```

Useful local URLs:

- API root: <http://127.0.0.1:8000/>
- Health check: <http://127.0.0.1:8000/health>
- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

Importing or starting the FastAPI application does not start the scheduler, execute collection, or make network requests.

## Read API

All V1 Hiring Intelligence routes are read-only:

| Method | Endpoint | Behavior |
|---|---|---|
| `GET` | `/api/v1/hiring/jobs` | Lists jobs with optional `organization`, `country`, and `employment_type` filters plus `limit`/`offset` pagination. |
| `GET` | `/api/v1/hiring/jobs/{job_id}` | Returns one persisted job or `404`. |
| `GET` | `/api/v1/hiring/jobs/{job_id}/evidence` | Returns evidence linked through the job's persisted `evidence_id`. |
| `GET` | `/api/v1/hiring/runs` | Lists recent collection runs with optional `organization` and `limit`. |
| `GET` | `/api/v1/hiring/runs/{run_id}` | Returns one collection run or `404`. |

Job list defaults are `limit=25` and `offset=0`; the maximum limit is 100. Run lists default to 20 with a maximum of 100. Invalid UUIDs, enums, limits, and offsets return `422` through FastAPI validation.

The API exposes normalized domain records only. It does not expose raw Workday search or detail payloads.

## Configuration

Settings use the `BSI_` environment prefix.

| Environment variable | Default | Purpose |
|---|---:|---|
| `BSI_SQLITE_DATABASE_PATH` | `data/hiring-intelligence.sqlite3` | Local SQLite database location. |
| `BSI_WELLS_FARGO_REQUEST_TIMEOUT_SECONDS` | `20.0` | Timeout for public Workday requests. |
| `BSI_WELLS_FARGO_RETRY_COUNT` | `2` | Retry count for rate limits and transient server errors. |
| `BSI_WELLS_FARGO_SCHEDULE_ENABLED` | `false` | Enables the configured scheduled job when the scheduler is explicitly invoked. |
| `BSI_WELLS_FARGO_SCHEDULE_INTERVAL_SECONDS` | `86400` | Interval measured from the previous run's completion. |
| `BSI_WELLS_FARGO_SCHEDULE_MAX_PAGES` | `1` | Maximum pages per scheduled run. |
| `BSI_WELLS_FARGO_SCHEDULE_MAX_RECORDS` | `20` | Maximum records processed per scheduled run. |

Example:

```bash
export BSI_SQLITE_DATABASE_PATH=data/local-hiring.sqlite3
export BSI_WELLS_FARGO_REQUEST_TIMEOUT_SECONDS=20
export BSI_WELLS_FARGO_RETRY_COUNT=0
```

Do not commit `.env` files, credentials, or local databases. The public Workday source does not require credentials.

## SQLite Persistence

The configured database is initialized lazily by the read API or explicitly by a composition factory. Local database files under `data/` are ignored by Git.

The schema stores:

- Normalized `JobPosting` records.
- `Evidence` records and provenance metadata.
- `CollectionRun` audit records.

Jobs are upserted using `(organization, source_job_id)`, so collecting the same Wells Fargo requisition again updates the existing record instead of creating a duplicate. Evidence linkage is enforced with `JobPosting.evidence_id`. Raw Workday payload archival is intentionally separate and is not implemented in V1.

## Evidence and Provenance

Every normalized job has a linked `Evidence` record containing:

- Public source URL and source title.
- Career-site source type.
- Retrieval timestamp.
- A deterministic, bounded source excerpt.
- Stable raw reference such as `workday:wf:WellsFargoJobs:<jobReqId>`.
- Collector identity and JSON-compatible provenance metadata.

The normalizer guarantees that `JobPosting.evidence_id` exactly matches `Evidence.evidence_id`. Business unit, capability, skill, technology, seniority, and leadership fields remain unpopulated unless supported by later deterministic or enrichment stages.

## Collection and Failure Behavior

`PaginatedJobCollector` processes opaque cursors sequentially, respects page and record limits, detects repeated cursors, and continues when individual records fail.

- Clean natural completion produces `completed`.
- Valid records mixed with record/detail failures produce `partial`; valid jobs are still persisted.
- A page failure after prior success produces `partial`.
- An initial source failure with no jobs produces `failed` and persists no fake jobs.
- Known persistence failures produce typed execution failures and attempt to preserve a failed run audit.
- Unexpected programming errors are not silently converted by the collection or execution layers.

Every execution uses its pipeline-generated `run_id` for `CollectionRun` observability.

## Scheduling

The scheduler is an in-memory, source-neutral interval scheduler. It invokes `HiringCollectionExecutionService`; it does not contain collector, normalization, SQL, or source-specific logic.

Scheduling is disabled by default and never starts on import. Enabling the setting alone does not start a background task. A host process must explicitly call `run_due_jobs()` or `start()` and must close the composition during shutdown.

For one tightly controlled scheduled execution using conservative limits:

```bash
export BSI_WELLS_FARGO_SCHEDULE_ENABLED=true
export BSI_WELLS_FARGO_SCHEDULE_MAX_PAGES=1
export BSI_WELLS_FARGO_SCHEDULE_MAX_RECORDS=20
export BSI_WELLS_FARGO_RETRY_COUNT=0

python - <<'PY'
import asyncio

from backend.app.infrastructure.composition.hiring_scheduling import (
    create_wells_fargo_scheduled_hiring_composition,
)


async def main():
    composition = create_wells_fargo_scheduled_hiring_composition()
    try:
        outcomes = await composition.scheduler.run_due_jobs()
        for outcome in outcomes:
            print(outcome.model_dump(mode="json"))
    finally:
        await composition.close()


asyncio.run(main())
PY
```

This command makes live public Workday requests when enabled. Review Wells Fargo's current public access rules before running it. For a long-running service, application lifecycle integration should explicitly call `scheduler.start()` and `scheduler.stop()`; that integration is intentionally not present in `main.py` yet.

## Wells Fargo Source Safety

The adapter uses the public Wells Fargo Workday CXS job search and job-detail endpoints only. Operate conservatively:

- Request a small number of pages and records.
- Respect `403`, `429`, rate limits, robots guidance, and applicable terms.
- Stop on restrictions; do not bypass authentication, CAPTCHAs, Cloudflare, or bot protections.
- Do not use proxies, rotating user agents, browser impersonation, or candidate/application endpoints.
- Do not submit data or crawl the full job inventory.
- Keep deterministic parsing and normalization free of LLM behavior.

## Current Limitations

- Wells Fargo is the only live source.
- SQLite and in-memory scheduling are intended for a local POC, not distributed production deployment.
- Scheduler state does not survive process restarts; `CollectionRun` remains the durable audit history.
- No authentication, authorization, API rate limiting, or write API exists.
- Query filters are exact and case-sensitive; pagination does not report a total match count.
- No schema migration framework or raw-source archive exists.
- No historical change analytics, hiring concentration analysis, enrichment, or signal scoring exists yet.
- No Strategy, Technology, Organization, Financial, News, Supervisor, or Opportunity agents are implemented.

## Logical Next Phase

The next platform phase should add deterministic intelligence-signal generation and additional research verticals, beginning with Strategy Intelligence and Organization Intelligence. Those capabilities can then feed a Supervisor Agent for cross-domain correlation. Consulting opportunity hypotheses should remain isolated in a later Opportunity Agent and should be generated only from correlated, traceable evidence—not independently by research agents.
