import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrganizationProvider } from "../context/OrganizationContext";
import { TechnologyIntelligencePage } from "./TechnologyIntelligencePage";

function withOrg(children: ReactNode) {
  return <OrganizationProvider value={{ organization: "Wells Fargo", setOrganization: vi.fn() }}>{children}</OrganizationProvider>;
}

const snapshot = { organization: "Wells Fargo", total_jobs: 19, enriched_jobs: 1, technology_observation_count: 2, unique_technologies: 2, technology_coverage_percentage: 5.26, observation_start: "2026-08-01", observation_end: "2026-08-20", generated_at: "2026-08-21T12:00:00Z" };
const reference = { job_id: "job-1", evidence_id: "evidence-1" };
const observation = { technology: "PowerBI", normalized_technology: "Power BI", category: "BI / Visualization", organization: "Wells Fargo", job_id: "job-1", job_title: "Senior Analytics Consultant", evidence_id: "evidence-1", source_type: "career_site", observation_date: "2026-08-20", location: "Charlotte, NC", business_unit: "Consumer Banking", seniority: "senior", confidence: 1, provenance: { provider: "vertex_gemini", model: "gemini-2.5-flash", prompt_schema_version: "hiring-enrichment-v3", enrichment_timestamp: "2026-08-21T12:00:00Z" }, support_references: [{ evidence_id: "evidence-1", excerpt: "Power BI" }] };

function ok(body: unknown) { return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })); }

afterEach(() => vi.unstubAllGlobals());

describe("TechnologyIntelligencePage", () => {
  it("renders coverage, technologies, and evidence traceability", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/summary")) return ok({ snapshot, coverage_limitation: "Limited coverage." });
      if (url.includes("/analytics")) return ok({ snapshot, top_technologies: [{ technology: "Power BI", category: "BI / Visualization", job_count: 1, observation_count: 1, percentage_of_enriched_jobs: 100, evidence_count: 1, contributing_records: [reference] }], categories: [{ category: "BI / Visualization", unique_technology_count: 1, observation_count: 1, job_count: 1, contributing_records: [reference] }], business_unit_technologies: [], geography_technologies: [], seniority_technologies: [] });
      if (url.includes("/signals")) return ok({ organization: "Wells Fargo", generated_at: "2026-08-21T12:00:00Z", total_jobs: 19, enriched_jobs: 1, enrichment_coverage: 1 / 19, technology_observation_count: 2, generated_signal_count: 0, signals: [], limitations: ["Low enrichment coverage."] });
      return ok({ items: [observation], total: 1, limit: 25, offset: 0, returned_count: 1 });
    }));
    render(withOrg(<TechnologyIntelligencePage />));
    expect(screen.getByText("Loading technology coverage…")).toBeInTheDocument();
    expect(await screen.findByText("Technology classifications are available for 1 of 19 observed hiring records.")).toBeInTheDocument();
    expect(screen.getAllByText("Power BI").length).toBeGreaterThan(0);
    expect(screen.getByText("Senior Analytics Consultant")).toBeInTheDocument();
    expect(screen.getByText("evidence…")).toBeInTheDocument();
    expect(screen.getByText("No deterministic technology signal met every configured support threshold.")).toBeInTheDocument();
  });

  it("renders populated deterministic signals with navigable evidence counts", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/summary")) return ok({ snapshot: { ...snapshot, total_jobs: 10, enriched_jobs: 5, technology_coverage_percentage: 50 }, coverage_limitation: "Limited coverage." });
      if (url.includes("/analytics")) return ok({ snapshot, top_technologies: [], categories: [], business_unit_technologies: [], geography_technologies: [], seniority_technologies: [] });
      if (url.includes("/signals")) return ok({ organization: "Wells Fargo", generated_at: "2026-08-21T12:00:00Z", total_jobs: 10, enriched_jobs: 5, enrichment_coverage: 0.5, technology_observation_count: 10, generated_signal_count: 1, signals: [{ signal_id: "signal-1", organization: "Wells Fargo", signal_type: "technology_concentration", title: "Observed hiring concentration for Python", summary: "Within the currently enriched hiring sample, Python appears in 3 enriched job records.", subject: "Python", observation_start: "2026-07-01", observation_end: "2026-08-20", confidence: 0.75, strength: 0.6, evidence_coverage: 1, supporting_job_ids: ["job-1"], supporting_evidence_ids: ["evidence-1"], limitations: ["Hiring evidence does not prove deployment."], provenance: { generator: "TechnologySignalService", configuration_version: "technology-signals-v1", deterministic: true } }], limitations: [] });
      return ok({ items: [], total: 0, limit: 25, offset: 0, returned_count: 0 });
    }));
    render(withOrg(<TechnologyIntelligencePage />));
    expect(await screen.findByText("Observed hiring concentration for Python")).toBeInTheDocument();
    expect(screen.getByText("1 evidence records")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View job" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View evidence" })).toBeInTheDocument();
  });

  it("renders error and empty states without production mocks", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input).includes("/observations")) return ok({ items: [], total: 0, limit: 25, offset: 0, returned_count: 0 });
      return Promise.reject(new Error("Backend unavailable"));
    }));
    render(withOrg(<TechnologyIntelligencePage />));
    expect((await screen.findAllByText("Backend unavailable")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("No technology observations are available for this organization.")).length).toBeGreaterThan(0);
  });
});
