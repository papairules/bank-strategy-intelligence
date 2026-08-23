import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrganizationProvider } from "../context/OrganizationContext";
import { OverviewPage } from "./OverviewPage";
import { summaryFixture } from "../test/fixtures";

function withOrg(children: ReactNode) {
  return <OrganizationProvider value={{ organization: "Wells Fargo", setOrganization: vi.fn() }}><MemoryRouter>{children}</MemoryRouter></OrganizationProvider>;
}

function ok(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

const technologySnapshot = { organization: "Wells Fargo", total_jobs: 19, enriched_jobs: 19, technology_observation_count: 24, unique_technologies: 23, technology_coverage_percentage: 100, observation_start: "2026-08-20", observation_end: "2026-08-21", generated_at: "2026-08-21T12:00:00Z" };
const evidenceSummary = { organization: "Wells Fargo", total_evidence_records: 19, total_jobs: 19, jobs_with_evidence: 19, evidence_coverage: 100, enriched_evidence_count: 19, enrichment_coverage: 100, evidence_supporting_hiring_signals: 19, evidence_supporting_technology_observations: 5, evidence_supporting_technology_signals: 4, source_distribution: [{ source: "Workday", source_type: "career_site", evidence_count: 19 }], observation_start: "2026-08-20", observation_end: "2026-08-21", generated_at: "2026-08-21T12:00:00Z" };
const strategyResult = { organization: "Wells Fargo", generated_at: "2026-08-21T12:00:00Z", generated_signal_count: 0, coverage_context: { total_jobs: 19, jobs_with_evidence: 19, hiring_evidence_coverage: 1, enriched_jobs: 19, enrichment_coverage: 1, hiring_signal_count: 3, technology_observation_count: 24, technology_signal_count: 2, observation_start: "2026-08-20", observation_end: "2026-08-21" }, signals: [], limitations: ["The observation period is shorter than the configured minimum.", "Evidence currently derives from a single public hiring source."] };

afterEach(() => vi.unstubAllGlobals());

describe("OverviewPage", () => {
  it("renders the fully enriched executive snapshot and governed entry points", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/hiring/") && url.includes("/summary")) return ok({ ...summaryFixture, total_observed_jobs: 19, jobs_with_evidence: 19, evidence_coverage: 100, enriched_job_count: 19, enrichment_coverage: 100, signal_count: 3, observation_start: "2026-08-20", observation_end: "2026-08-21" });
      if (url.includes("/technology/") && url.includes("/summary")) return ok({ snapshot: technologySnapshot, coverage_limitation: null });
      if (url.includes("/technology/") && url.includes("/signals")) return ok({ organization: "Wells Fargo", generated_at: "2026-08-21T12:00:00Z", total_jobs: 19, enriched_jobs: 19, enrichment_coverage: 1, technology_observation_count: 24, generated_signal_count: 2, signals: [], limitations: [] });
      if (url.includes("/evidence/") && url.includes("/summary")) return ok(evidenceSummary);
      return ok(strategyResult);
    }));
    render(withOrg(<OverviewPage />));
    expect(screen.getByText("Loading executive intelligence…")).toBeInTheDocument();
    expect(await screen.findByText("What the current evidence supports")).toBeInTheDocument();
    expect(screen.getAllByText("100%").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("Cross-domain conclusions are withheld")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ask Evidence/ })).toHaveAttribute("href", "/evidence#ask-evidence");
    expect(screen.getByRole("link", { name: /Ask Strategy/ })).toHaveAttribute("href", "/signals#ask-strategy");
  });

  it("renders a safe integrated error state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Backend unavailable"))));
    render(withOrg(<OverviewPage />));
    expect(await screen.findByText("One or more intelligence domains could not be loaded.")).toBeInTheDocument();
  });
});
