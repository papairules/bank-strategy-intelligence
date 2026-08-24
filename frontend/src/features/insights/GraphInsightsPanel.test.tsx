import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GraphInsightsPanel } from "./GraphInsightsPanel";

function ok(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const snapshot = {
  organization: "BNY",
  node_count: 318,
  edge_count: 1213,
  jobs_read: 1120,
  classified_jobs_used: 1120,
  enriched_jobs_used: 0,
  hiring_signals_used: 5,
  strategic_themes_used: 2,
  top_capabilities: [{ name: "Risk and Compliance", job_count: 361 }],
  top_technologies: [{ name: "Java", job_count: 128 }],
  top_locations: [{ name: "Charlotte, NC", job_count: 210 }],
  strategic_themes: [
    { name: "Cloud modernization", direction: "increase_investment", confidence: 0.65, time_horizon: "12 months", business_unit: null, evidence_count: 2 },
  ],
};

describe("GraphInsightsPanel", () => {
  it("renders strategic themes, geographic concentration, top capabilities, and top technologies in that order", async () => {
    vi.stubGlobal("fetch", vi.fn(() => ok(snapshot)));

    render(<GraphInsightsPanel organization="BNY" />);

    expect(await screen.findByText("Cloud modernization")).toBeInTheDocument();
    expect(screen.getByText("Increase Investment")).toBeInTheDocument();
    expect(screen.getByText("Charlotte, NC")).toBeInTheDocument();
    expect(screen.getByText("Risk and Compliance")).toBeInTheDocument();
    expect(screen.getByText("Java")).toBeInTheDocument();
    expect(screen.getByText("2 evidence records")).toBeInTheDocument();

    const grid = document.querySelector<HTMLElement>(".graph-insights__grid")!;
    const headings = within(grid).getAllByRole("heading", { level: 3 }).map((item) => item.textContent);
    expect(headings).toEqual(["Geographic concentration", "Top capabilities", "Top technologies"]);
  });

  it("shows an empty-state message when no strategic themes are cached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => ok({ ...snapshot, strategic_themes: [], strategic_themes_used: 0 })));

    render(<GraphInsightsPanel organization="BNY" />);

    expect(await screen.findByText(/No Strategy Agent research is cached/)).toBeInTheDocument();
  });

  it("renders an error state when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Backend unavailable"))));

    render(<GraphInsightsPanel organization="BNY" />);

    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
  });
});
