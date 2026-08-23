import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrganizationProvider } from "../context/OrganizationContext";
import { HiringIntelligencePage } from "./HiringIntelligencePage";
import { analyticsFixture, jobsFixture, signalsFixture, summaryFixture } from "../test/fixtures";

function withOrg(children: ReactNode) {
  return <OrganizationProvider value={{ organization: "Wells Fargo", setOrganization: vi.fn() }}>{children}</OrganizationProvider>;
}

function response(body: unknown) { return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })); }

afterEach(() => vi.unstubAllGlobals());

describe("HiringIntelligencePage", () => {
  it("renders the real API summary and jobs", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/summary")) return response(summaryFixture);
      if (url.includes("/analytics")) return response(analyticsFixture);
      if (url.includes("/signals")) return response(signalsFixture);
      if (url.includes("/graph-insights/")) return response({ organization: "Wells Fargo", node_count: 0, edge_count: 0, jobs_read: 0, classified_jobs_used: 0, enriched_jobs_used: 0, hiring_signals_used: 0, strategic_themes_used: 0, top_capabilities: [], top_technologies: [], strategic_themes: [] });
      return response(jobsFixture);
    }));
    render(withOrg(<HiringIntelligencePage />));
    expect(screen.getByText("Loading executive summary…")).toBeInTheDocument();
    expect(await screen.findByText("Observed jobs")).toBeInTheDocument();
    expect(screen.getByText("Senior Analytics Consultant")).toBeInTheDocument();
    expect(screen.getByText("No intelligence signals generated for the current observation period.")).toBeInTheDocument();
  });

  it("renders a safe error state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Backend unavailable"))));
    render(withOrg(<HiringIntelligencePage />));
    expect((await screen.findAllByText("Backend unavailable")).length).toBeGreaterThan(0);
  });
});
