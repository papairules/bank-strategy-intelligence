# Account Growth Intelligence

Account Growth Intelligence turns public hiring evidence into a governed, evidence-traceable account-growth report for banking organizations. It combines deterministic hiring analytics, an LLM-assisted knowledge graph, and a set of governed AI agents (including one with live web search) into a single consolidated per-organization workspace: the "Company Report" you'd use to find where a bank account is worth pursuing next, backed by hiring signals rather than guesswork.

This document reflects the current (v2) state of the project — a full-stack app (FastAPI + React/Vite) with multi-bank coverage, LLM enrichment, deterministic signal generation, a knowledge graph, and five governed agents. It supersedes the original V1 scope, which was a Wells-Fargo-only, backend-only collection pipeline with no frontend or AI.

## Current State

- **Multi-bank coverage.** Six organizations are supported end-to-end: Wells Fargo, BNY, Goldman Sachs, Citibank, Morgan Stanley, and Barclays (`frontend/src/config/organization.ts`). Wells Fargo has a live public-source collector (`infrastructure/collectors/hiring/sources/wells_fargo`); the other five organizations' job postings were imported from per-organization CSV snapshots (`data/csv/active_jobs_<org>_<timestamp>.csv`) into the same canonical `JobPosting`/`Evidence` domain models, not a live scheduled crawl.
- **Deterministic ingestion, still intact from V1.** Source-neutral pagination, cursor protection, partial-failure handling, `CollectionRun` audit records, and SQLite persistence with idempotent upserts.
- **LLM-assisted enrichment.** Per-job capability/skills/technology/seniority classification (`application/hiring/enrichment.py`), with every extracted value checked against the actual source text before being trusted — ungrounded model output is dropped, not displayed.
- **Deterministic analytics and signal generation (no LLM).** Hiring concentration signals (geography, capability, leadership, volume, trend), technology observations (LLM-enriched *and* zero-cost keyword-matched), and cross-domain signals that require the *same* job IDs to independently support both a hiring and a technology finding before a pattern is surfaced.
- **A per-organization knowledge graph.** `application/hiring/kg/` builds a disk-cached NetworkX graph (jobs, evidence, capabilities, technologies, locations, business units, strategic themes) and exposes a cheap read model for the UI.
- **Five governed agents**, each with a distinct role — see [Agents](#agents) below.
- **A consolidated React/Vite frontend** — a single "Workspace" page per organization (see [Frontend](#frontend-workspace)).
- **Cloud Run deployment** — the backend serves the built frontend as a single service (`Procfile`, `.gcloudignore`).

## Agents

| Agent | What it does | Live web search? | Endpoint |
|---|---|---|---|
| **Evidence Agent** | Answers grounded questions strictly over persisted evidence, via tool calls with citation validation against what the tools actually returned. | No | `POST /api/v1/agents/evidence/answer` |
| **Hiring Agent** | LLM-assisted classification of persisted jobs into capability/business-unit/seniority hiring signals — an alternate, LLM-driven view distinct from the deterministic signal generator. | No | `POST /api/v1/agents/hiring/answer` |
| **Strategy Agent** | A 7-stage LangGraph pipeline: plans research queries, runs real OpenAI web search, extracts evidence, drafts strategic signals, runs a quality-review pass, and scores confidence. Cached per (organization, question, time horizon). | **Yes** | `POST /api/v1/agents/strategy/answer` |
| **Supervisor Agent** | Orchestrates report generation: calls the Strategy Agent, rebuilds the knowledge graph, regenerates deterministic hiring signals, then validates/scores/combines everything into 30/60/90/180/360-day opportunity horizons. Runs no research of its own. | No (delegates to Strategy Agent) | `POST /api/v1/agents/supervisor/report` |
| **Report QA** | Single structured LLM call answering a follow-up question strictly from an already-generated report payload; its response schema is dynamically constrained so it cannot cite a reference that isn't in that report. | No | `POST /api/v1/agents/supervisor/report/answer` |

## Frontend (Workspace)

The frontend is a single consolidated page per organization (`frontend/src/pages/OverviewPage.tsx`), reached via the sidebar's "Workspace" entry. In order:

1. **Hiring Intelligence** — observed-jobs metrics, top hiring geography/capability, and a weekly hiring-cadence chart.
2. **Company Report** — the primary deliverable: generate an evidence-backed account report (executive summary, opportunity outlook table, sources, methodology/limitations) plus a report-scoped Q&A chat.
3. **Knowledge Graph** — geographic concentration, top capabilities, and top technologies read from the cached per-organization graph.

A fourth section, **Strategic Signals** (an open-ended, live-web-search chat via the Strategy Agent), was removed from the Workspace page by product decision but the component (`features/strategy/AskStrategyPanel.tsx`) and its standalone route (`/signals`) are still in the codebase, just unlinked from navigation.

## Architecture

```text
Public source (Wells Fargo Workday CXS) / imported records (other 5 banks)
    -> Source adapter / import -> PaginatedJobCollector -> Normalizer
    -> JobPosting + Evidence (SQLite, CollectionRun audit)
    -> HiringEnrichmentService (LLM, grounded against source text)
    -> Deterministic analytics & signal generation
         (HiringAnalyticsService, HiringSignalService,
          TechnologyAnalyticsService, CrossDomainStrategicSignalService)
    -> HiringKnowledgeGraphService (per-org, disk-cached graph)
    -> Agents (Evidence, Hiring, Strategy, Supervisor, Report QA)
    -> FastAPI read + agent API (/api/v1/*)
    -> React/Vite frontend (single-page Workspace)
```

Source-specific parsing stays isolated under `infrastructure/`; domain models, execution, scheduling, and persistence protocols do not depend on any one source.

## Package Structure

```text
backend/app/
├── api/v1/                        # FastAPI routes: hiring, technology, evidence, strategy, graph_insights, agents
├── application/
│   ├── agents/                    # evidence_agent, hiring_agent, strategy_agent, supervisor_agent
│   ├── hiring/                    # collection, enrichment, analytics, signal_generation, kg/
│   ├── technology/                # technology observation/analytics/signals
│   ├── evidence/                  # unified evidence read model
│   └── strategy/                  # cross-domain deterministic signal service
├── domain/                        # JobPosting, Evidence, intelligence signal contracts
├── infrastructure/
│   ├── collectors/hiring/         # PaginatedJobCollector + source adapters (wells_fargo)
│   ├── composition/                # DI wiring, one file per agent/service
│   ├── llm/                        # openai/ and vertex/ provider clients
│   └── persistence/hiring/         # SQLite repositories
├── config.py                      # BSI_-prefixed environment settings
└── main.py                        # FastAPI entry point; serves frontend/dist when built

frontend/src/
├── pages/                         # OverviewPage (Workspace) + unlinked standalone pages
├── features/                      # hiring/, report/, strategy/, insights/, evidence/
├── api/, components/, context/, hooks/, layouts/, types/, utils/

tests/                             # backend: api/, unit/
```

## Requirements

- Python 3.13+
- Node.js 18+ and `npm`
- An OpenAI API key to exercise any LLM-backed feature (enrichment, agents) — everything else runs without one

SQLite is provided by Python's standard library; no external database service is required.

## Setup

```bash
git clone <repository-url>
cd bank-strategy-intelligence
python3.13 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
python -m pip install --upgrade pip
pip install -e ".[dev]"

cd frontend
npm install
```

Create a `.env` at the repo root for local secrets (never commit it) — see [Configuration](#configuration).

## Run Tests

```bash
pytest                # backend, fully offline
cd frontend && npm test   # frontend (Vitest)
```

## Run Locally

**Split dev mode** (hot reload on both sides):

```bash
uvicorn backend.app.main:app --reload      # backend on :8000
cd frontend && npm run dev                 # frontend on :5173 (or next free port)
```

**Combined mode** (matches production/Cloud Run — one process serves both):

```bash
cd frontend && npm run build
uvicorn backend.app.main:app --reload      # serves frontend/dist at "/"
```

Useful local URLs: API root `http://127.0.0.1:8000/`, health check `/health`, Swagger UI `/docs`.

## API Surface

| Route group | Purpose |
|---|---|
| `GET /api/v1/hiring/...` | Read-only jobs, evidence links, collection runs, summary/analytics/signals |
| `GET /api/v1/technology/...` | Technology observation summary/analytics/signals |
| `GET /api/v1/evidence/...` | Unified evidence records and summary |
| `GET /api/v1/strategy/organizations/{organization}/signals` | Deterministic cross-domain signals (not the Strategy Agent) |
| `GET /api/v1/graph-insights/organizations/{organization}` | Cached knowledge-graph read model |
| `POST /api/v1/agents/*` | The five governed agents — see [Agents](#agents) |

All non-agent routes are read-only. Job list defaults are `limit=25`/`offset=0` (max 100); invalid UUIDs/enums/limits return `422`.

## Configuration

All settings use the `BSI_` environment prefix (`backend/app/config.py`).

| Environment variable | Default | Purpose |
|---|---:|---|
| `BSI_SQLITE_DATABASE_PATH` | `data/hiring-intelligence.sqlite3` | SQLite database location. |
| `BSI_HIRING_KG_GRAPH_DIRECTORY` | `data/graphs` | Disk cache for per-organization knowledge graphs. |
| `BSI_WELLS_FARGO_REQUEST_TIMEOUT_SECONDS` | `20.0` | Timeout for public Workday requests. |
| `BSI_WELLS_FARGO_RETRY_COUNT` | `2` | Retry count for rate limits/transient errors. |
| `BSI_WELLS_FARGO_SCHEDULE_ENABLED` | `false` | Enables the scheduled collection job when explicitly invoked. |
| `BSI_WELLS_FARGO_SCHEDULE_INTERVAL_SECONDS` | `86400` | Interval from the previous run's completion. |
| `BSI_WELLS_FARGO_SCHEDULE_MAX_PAGES` / `_MAX_RECORDS` | `1` / `20` | Per-run scheduled limits. |
| `BSI_HIRING_ENRICHMENT_ENABLED` | `false` | Enables LLM-assisted per-job enrichment. |
| `BSI_HIRING_LLM_PROVIDER` | `vertex_gemini` | Enrichment provider. |
| `BSI_GEMINI_MODEL` | `gemini-2.5-flash` | Model for Gemini-backed enrichment. |
| `BSI_EVIDENCE_AGENT_ENABLED` | `false` | Enables the Evidence Agent. |
| `BSI_EVIDENCE_AGENT_MODEL` | `gemini-2.5-flash` | Evidence Agent model. |
| `BSI_STRATEGY_AGENT_ENABLED` | `false` | Enables the live-web-search Strategy Agent. |
| `BSI_STRATEGY_AGENT_PROVIDER` | `openai_web` | Strategy Agent provider. |
| `BSI_STRATEGY_AGENT_CACHE_TTL_HOURS` | `24.0` | How long an identical (org, question, time horizon) answer is reused before re-researching. |
| `BSI_HIRING_AGENT_ENABLED` | `false` | Enables the LLM-assisted Hiring Agent. |
| `BSI_HIRING_AGENT_MAX_JOBS` | unset | Caps jobs classified per Hiring Agent run. |
| `BSI_SUPERVISOR_AGENT_ENABLED` | `false` | Enables Company Report generation. |
| `BSI_REPORT_QA_ENABLED` | `false` | Enables the report Q&A chat. |
| `BSI_OPENAI_API_KEY` | unset | OpenAI credential used by the Strategy Agent, Supervisor, and Report QA. |
| `BSI_OPENAI_MODEL` | `gpt-5.4-mini` | Model used by OpenAI-backed agents. |

Example minimal local setup with agents enabled:

```bash
export BSI_STRATEGY_AGENT_ENABLED=true
export BSI_SUPERVISOR_AGENT_ENABLED=true
export BSI_REPORT_QA_ENABLED=true
export BSI_HIRING_AGENT_ENABLED=true
export BSI_OPENAI_API_KEY=<your-key>
```

Do not commit `.env` files or credentials. Note: unlike a typical setup, `data/` (the SQLite database, per-organization knowledge-graph cache, CSV snapshots, and the Hiring Agent's job-page fetch cache) is currently checked into this repo rather than gitignored — the relevant `.gitignore` rules exist but are commented out. Worth revisiting before this grows further.

## Deployment (Cloud Run)

The backend serves the built frontend as a single service — no separate frontend host is required.

```bash
cd frontend && npm run build      # produces frontend/dist
gcloud run deploy <service-name> --source . --region <your-region>
```

`Procfile` (`web: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`) and `.gcloudignore` are already configured for buildpack-based deploys. Deploy with `--no-traffic` and a `--tag` to preview a new revision before shifting production traffic.

## Current Limitations

- SQLite and in-memory scheduling remain a local/single-service POC scope, not a distributed production deployment.
- Only Wells Fargo has a live, scheduled public-source collector; the other five organizations rely on imported snapshots.
- Enrichment coverage varies significantly by organization — reports for low-coverage organizations will have noticeably thinner hiring/technology findings.
- Cross-domain deterministic signals require fairly strict minimums (jobs, enrichment coverage, observation window) and commonly read `0` on smaller datasets — this is expected, not a bug.
- Company Report generation is not itself cached — regenerating the same report re-runs the full Supervisor synthesis every time, even though the Strategy Agent's own sub-call is cached.
- No authentication, authorization, or write API exists.
- No report export/print/share mechanism — a generated report only persists in the browser's session storage.

## Known Gaps / Improvement Ideas

- The Company Report's `strategic_priorities`, `cross_domain_alignment`, `business_areas_to_watch`, and `opportunity_horizons` fields are already generated by `DeterministicReportGenerator` but are not yet rendered in `CompanyReportBody.tsx` — the outlook table and executive summary are the only parts of that data currently surfaced to the user.
- Report-level caching (beyond the existing Strategy Agent cache) would make repeat views of the same account meaningfully cheaper and faster.
- A basic export/copy action for a generated report would materially improve its usefulness for the account-growth workflow this tool is built around.
