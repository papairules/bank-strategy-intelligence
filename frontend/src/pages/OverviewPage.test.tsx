import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OrganizationProvider } from "../context/OrganizationContext";
import { OverviewPage } from "./OverviewPage";
import { analyticsFixture } from "../test/fixtures";

function withOrg(children: ReactNode) {
  return <OrganizationProvider value={{ organization: "Wells Fargo", setOrganization: vi.fn() }}><MemoryRouter>{children}</MemoryRouter></OrganizationProvider>;
}

function ok(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

const graphInsights = {
  organization: "Wells Fargo", node_count: 0, edge_count: 0, jobs_read: 19, classified_jobs_used: 19, enriched_jobs_used: 0, hiring_signals_used: 0, strategic_themes_used: 0,
  top_capabilities: [{ name: "Risk & Compliance", job_count: 12 }],
  top_technologies: [{ name: "Python", job_count: 8 }],
  top_locations: [{ name: "Charlotte, NC", job_count: 9 }],
  strategic_themes: [],
};
const supervisorReportResponse = {
  organization: "Wells Fargo", strategy_signal_count: 0, hiring_signal_count: 0,
  coverage: { total_jobs: 19, enriched_jobs: 19, enrichment_coverage_percentage: 100, kg_enriched_job_count: 0, limitations: [] },
  report: {
    organization: "Wells Fargo", total_hiring_jobs: 19, executive_summary: "Evidence supports a focused hiring pattern.", strategic_priorities: [], hiring_intelligence: [], cross_domain_alignment: [], business_areas_to_watch: [],
    lob_opportunities: [], evidence_traceability: [], limitations: [],
  }, provider: "openai", model: "test-model",
};

function stubOverviewFetch() {
  const fetch = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/agents/supervisor/report")) return ok(supervisorReportResponse);
    if (url.includes("/hiring/") && url.includes("/analytics")) return ok(analyticsFixture);
    if (url.includes("/graph-insights/")) return ok(graphInsights);
    return Promise.reject(new Error(`unexpected fetch: ${url}`));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

beforeEach(() => window.sessionStorage.clear());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("OverviewPage", () => {
  it("renders every section as a single scroll, in order, with no header banner or jump nav", async () => {
    const fetch = stubOverviewFetch();
    render(withOrg(<OverviewPage />));

    expect(screen.queryByText("Loading executive intelligence…")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Intelligence context")).not.toBeInTheDocument();
    expect(screen.queryByText("What the current evidence supports")).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Report sections" })).not.toBeInTheDocument();

    expect(await screen.findByText("Observed hiring cadence")).toBeInTheDocument();
    expect(screen.queryByText("Observed jobs")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence scope")).not.toBeInTheDocument();
    expect(await screen.findByText("Evidence supports a focused hiring pattern.")).toBeInTheDocument();
    expect(await screen.findByText("Charlotte, NC")).toBeInTheDocument();
    expect(screen.queryByLabelText("Strategic question")).not.toBeInTheDocument();

    const dividers = Array.from(document.querySelectorAll(".intelligence-divider span")).map((item) => item.textContent);
    expect(dividers).toEqual(["Hiring intelligence", "Company report", "Knowledge graph insights"]);

    expect(fetch.mock.calls.some(([input]) => String(input).includes("/agents/supervisor/report"))).toBe(true);
    expect(fetch.mock.calls.some(([input]) => String(input).includes("/agents/strategy/answer"))).toBe(false);
  });

  it("generates the company report inline, scoped to the current organization", async () => {
    const fetch = stubOverviewFetch();
    render(withOrg(<OverviewPage />));
    await screen.findByText("Observed hiring cadence");
    await screen.findByText("Evidence supports a focused hiring pattern.");

    const reportCall = fetch.mock.calls.find(([input]) => String(input).includes("/agents/supervisor/report"));
    expect(reportCall).toBeDefined();
    expect(JSON.parse(String(reportCall![1]?.body))).toEqual({ organization: "Wells Fargo" });
  });

  it("shows each section's own error state when the backend is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Backend unavailable"))));
    render(withOrg(<OverviewPage />));
    expect((await screen.findAllByText("Backend unavailable")).length).toBeGreaterThan(0);
  });
});
