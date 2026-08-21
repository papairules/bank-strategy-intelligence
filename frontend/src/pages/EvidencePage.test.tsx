import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EvidencePage } from "./EvidencePage";

const record = { evidence_id: "508eb56f-52dd-54b9-a35f-6e96b3986105", organization: "Wells Fargo", source: "Workday", source_type: "career_site", source_url: "https://example.test/job", captured_at: "2026-08-21T03:46:43Z", observed_at: "2026-08-20", job_id: "ea62e879-bdcb-5785-8b11-a1755bd7c6ea", job_title: "Senior Analytics Consultant", job_location: "Bengaluru, India", business_unit: "Consumer Banking Lending", enrichment_present: true, enrichment_provider: "vertex_gemini", enrichment_model: "gemini-2.5-flash", enrichment_schema_version: "hiring-enrichment-v3", application_confidence: 0.95, technologies: ["Python", "SQL"], capabilities: ["Data & Analytics"], skills: ["analytics"], seniority: "senior", related_hiring_signals: [{ signal_id: "signal-1", signal_type: "hiring_volume", title: "Observed hiring volume" }], related_technology_observation_count: 2, related_technology_signals: [], evidence_preview: "Python and SQL analytics role." };
const summary = { organization: "Wells Fargo", total_evidence_records: 19, total_jobs: 19, jobs_with_evidence: 19, evidence_coverage: 100, enriched_evidence_count: 1, enrichment_coverage: 5.26, evidence_supporting_hiring_signals: 19, evidence_supporting_technology_observations: 1, evidence_supporting_technology_signals: 0, source_distribution: [{ source: "Workday", source_type: "career_site", evidence_count: 19 }], observation_start: "2026-08-20", observation_end: "2026-08-21", generated_at: "2026-08-21T04:00:00Z" };
const detail = { ...record, source_excerpt: "Python and SQL analytics role.", raw_reference: "workday:R-1", collector_identity: "collector", provenance_metadata: {}, enrichment_limitations: ["Hiring evidence only."], technology_observations: [{ technology: "Python", category: "Programming Language", confidence: 1, support_excerpt: "Python" }, { technology: "SQL", category: "Database", confidence: 1, support_excerpt: "SQL" }] };
function ok(body: unknown) { return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })); }
afterEach(() => vi.unstubAllGlobals());

describe("EvidencePage", () => {
  it("renders summary, records, enriched state, and detail relationships", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/summary")) return ok(summary);
      if (url.includes(`/evidence/${record.evidence_id}`)) return ok(detail);
      return ok({ items: [record], total: 1, limit: 25, offset: 0, returned_count: 1 });
    }));
    const user = userEvent.setup();
    render(<EvidencePage />);
    expect(await screen.findByText("Evidence records")).toBeInTheDocument();
    expect(screen.getByText("Senior Analytics Consultant")).toBeInTheDocument();
    expect(screen.getByText("Enriched")).toBeInTheDocument();
    await user.click(screen.getByText("508eb56f…"));
    expect(await screen.findByText("Source evidence")).toBeInTheDocument();
    expect(screen.getByText("AI enrichment")).toBeInTheDocument();
    expect(screen.getByText("Python · Programming Language · 100% confidence")).toBeInTheDocument();
    expect(screen.getByText("Observed hiring volume · hiring_volume")).toBeInTheDocument();
    expect(screen.getByText("No technology strategic signals currently cite this evidence because enrichment coverage is below the configured signal threshold.")).toBeInTheDocument();
  });

  it("renders source-only and empty records honestly", async () => {
    const sourceOnly = { ...record, evidence_id: "source-only", enrichment_present: false, enrichment_provider: null, enrichment_model: null, enrichment_schema_version: null, application_confidence: null, technologies: [], capabilities: [], skills: [], seniority: null, related_hiring_signals: [], related_technology_observation_count: 0 };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).includes("/summary") ? ok(summary) : ok({ items: [sourceOnly], total: 1, limit: 25, offset: 0, returned_count: 1 })));
    render(<EvidencePage />);
    expect(await screen.findByText("Source only")).toBeInTheDocument();
  });

  it("renders loading, error, and empty states", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).includes("/records") ? ok({ items: [], total: 0, limit: 25, offset: 0, returned_count: 0 }) : Promise.reject(new Error("Backend unavailable"))));
    render(<EvidencePage />);
    expect(screen.getByText("Loading evidence summary…")).toBeInTheDocument();
    expect((await screen.findAllByText("Backend unavailable")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("No evidence records match the current filters.")).length).toBeGreaterThan(0);
  });
});
