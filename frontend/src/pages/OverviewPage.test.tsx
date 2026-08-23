import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrganizationProvider, useOrganization } from "../context/OrganizationContext";
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

function stubOverviewFetch() {
  const fetch = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/hiring/") && url.includes("/summary")) return ok({ ...summaryFixture, total_observed_jobs: 19, jobs_with_evidence: 19, evidence_coverage: 100, enriched_job_count: 19, enrichment_coverage: 100, signal_count: 3, observation_start: "2026-08-20", observation_end: "2026-08-21" });
    if (url.includes("/technology/") && url.includes("/summary")) return ok({ snapshot: technologySnapshot, coverage_limitation: null });
    if (url.includes("/technology/") && url.includes("/signals")) return ok({ organization: "Wells Fargo", generated_at: "2026-08-21T12:00:00Z", total_jobs: 19, enriched_jobs: 19, enrichment_coverage: 1, technology_observation_count: 24, generated_signal_count: 2, signals: [], limitations: [] });
    if (url.includes("/evidence/") && url.includes("/summary")) return ok(evidenceSummary);
    return ok(strategyResult);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("OverviewPage", () => {
  it("renders the compact dynamic executive overview", async () => {
    const fetch = stubOverviewFetch();
    render(withOrg(<OverviewPage />));
    expect(screen.getByText("Loading executive intelligence…")).toBeInTheDocument();
    expect(await screen.findByText("What the current evidence supports")).toBeInTheDocument();
    const context = screen.getByLabelText("Intelligence context");
    expect(within(context).getByText("Organization")).toBeInTheDocument();
    expect(within(context).getByText("Wells Fargo")).toBeInTheDocument();
    expect(within(context).getByText("Observation period")).toBeInTheDocument();
    expect(within(context).getByText("Source evidence coverage")).toBeInTheDocument();
    expect(within(context).getByText("AI enrichment coverage")).toBeInTheDocument();
    expect(within(context).getAllByText("100%")).toHaveLength(2);

    const snapshot = screen.getByText("What the current evidence supports").closest("section")!;
    for (const label of ["Observed jobs", "Hiring signals", "Strategic signals"]) expect(within(snapshot).getByText(label)).toBeInTheDocument();
    expect(within(snapshot).getByText("19")).toBeInTheDocument();
    expect(within(snapshot).getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Hiring activity in context")).toBeInTheDocument();
    expect(screen.getByText("Cross-domain conclusions are withheld")).toBeInTheDocument();
    expect(screen.getByText("Evidence-backed company outlook")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View Hiring Intelligence/ })).toHaveAttribute("href", "/hiring");
    expect(screen.getByRole("link", { name: /View Strategic Signals/ })).toHaveAttribute("href", "/signals");
    expect(screen.getByRole("link", { name: /View Company Report/ })).toHaveAttribute("href", "/report");
    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(fetch.mock.calls.some(([input]) => String(input).includes("/agents/supervisor/report"))).toBe(false);

    for (const removed of ["Evidence records", "Unique technologies", "Technology observations", "Evidence & traceability", "Supports observations", "Supports tech signals", "A bounded technology footprint"]) expect(screen.queryByText(removed, { exact: false })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Intelligence provenance flow")).not.toBeInTheDocument();
  });

  it("preserves selected-company scope when opening Company Report", async () => {
    stubOverviewFetch();
    function ReportScope() {
      return <span>Report scope: {useOrganization().organization}</span>;
    }
    render(<OrganizationProvider value={{ organization: "BNY", setOrganization: vi.fn() }}><MemoryRouter><Routes><Route index element={<OverviewPage />} /><Route path="report" element={<ReportScope />} /></Routes></MemoryRouter></OrganizationProvider>);

    await userEvent.click(await screen.findByRole("link", { name: /View Company Report/ }));

    expect(screen.getByText("Report scope: BNY")).toBeInTheDocument();
  });

  it("renders a safe integrated error state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Backend unavailable"))));
    render(withOrg(<OverviewPage />));
    expect(await screen.findByText("One or more intelligence domains could not be loaded.")).toBeInTheDocument();
  });
});
