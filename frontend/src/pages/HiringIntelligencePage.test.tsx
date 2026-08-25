import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OrganizationProvider } from "../context/OrganizationContext";
import { HiringIntelligencePage } from "./HiringIntelligencePage";
import { analyticsFixture } from "../test/fixtures";

function withOrg(children: ReactNode) {
  return <OrganizationProvider value={{ organization: "Wells Fargo", setOrganization: vi.fn() }}>{children}</OrganizationProvider>;
}

function response(body: unknown) { return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })); }

afterEach(() => vi.unstubAllGlobals());

describe("HiringIntelligencePage", () => {
  it("renders only the hiring analytics cadence chart", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/analytics")) return response(analyticsFixture);
      return Promise.reject(new Error(`unexpected fetch: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(withOrg(<HiringIntelligencePage />));
    expect(screen.getByText("Loading hiring analytics…")).toBeInTheDocument();
    expect(await screen.findByText("Observed hiring cadence")).toBeInTheDocument();
    // Metrics grid, context strip, strategic hiring signals, job explorer,
    // knowledge graph, and the hiring agent no longer render on this page.
    // Geographic and capability concentration moved into the Knowledge
    // Graph section on the Overview page.
    expect(screen.queryByText("Observed jobs")).not.toBeInTheDocument();
    expect(screen.queryByText("Observation period")).not.toBeInTheDocument();
    expect(screen.queryByText("Strategic hiring signals")).not.toBeInTheDocument();
    expect(screen.queryByText("Job explorer")).not.toBeInTheDocument();
    expect(screen.queryByText("Cross-domain graph insights")).not.toBeInTheDocument();
    expect(screen.queryByText("Classify Hiring Signals")).not.toBeInTheDocument();
    expect(screen.queryByText("Geographic concentration")).not.toBeInTheDocument();
    expect(screen.queryByText("Capability concentration")).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("renders a safe error state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Backend unavailable"))));
    render(withOrg(<HiringIntelligencePage />));
    expect((await screen.findAllByText("Backend unavailable")).length).toBeGreaterThan(0);
  });
});
