import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { strategyAgentApi } from "../api/strategyAgent";
import { OrganizationProvider } from "../context/OrganizationContext";
import { StrategicSignalsPage } from "./StrategicSignalsPage";

vi.mock("../api/strategyAgent", () => ({ strategyAgentApi: { answer: vi.fn() } }));

const apiMock = vi.mocked(strategyAgentApi.answer);

function renderPage(organization: "Wells Fargo" | "BNY" = "Wells Fargo") {
  return render(
    <OrganizationProvider value={{ organization, setOrganization: vi.fn() }}>
      <MemoryRouter><StrategicSignalsPage /></MemoryRouter>
    </OrganizationProvider>,
  );
}

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("StrategicSignalsPage", () => {
  it("makes Ask Strategy primary without loading deterministic signals", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL) => Promise.resolve(new Response(JSON.stringify({
      organization: "Wells Fargo", node_count: 0, edge_count: 0, jobs_read: 0,
      classified_jobs_used: 0, enriched_jobs_used: 0, hiring_signals_used: 0,
      strategic_themes_used: 0, top_capabilities: [], top_technologies: [], strategic_themes: [],
    }), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    expect(screen.getByRole("heading", { name: "Evidence-grounded strategic research" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ask Strategy" })).toBeInTheDocument();
    expect(screen.getByLabelText("Strategic question")).toBeInTheDocument();
    expect(screen.getByLabelText(/Time horizon/)).toBeInTheDocument();
    expect(screen.queryByText("Cross-domain strategic signals")).not.toBeInTheDocument();
    expect(screen.queryByText(/hiring contributors/)).not.toBeInTheDocument();
    expect(screen.queryByText("Relevant Hiring Jobs")).not.toBeInTheDocument();
    // Only the cheap, disk-cached graph-insights read is fetched on mount;
    // deterministic hiring/strategy signal generation is never triggered here.
    await screen.findByText(/No Strategy Agent research is cached/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/graph-insights/");
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("uses the selected company scope and preserves Analyze behavior", async () => {
    apiMock.mockResolvedValue({
      status: "answered", organization: "BNY", question: "What changed recently?",
      executive_summary: "Recent evidence supports a focused transformation pattern.", findings: [],
      reliability: 0.8, limitations: [], tool_calls_used: 2, provider: "openai", model: "test-model",
      agent_version: "strategy-orchestrator-v1", strategic_signals: [],
    });
    renderPage("BNY");
    expect(screen.getByText(/recent developments for BNY/)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Strategic question"), "What changed recently?");
    await user.type(screen.getByLabelText(/Time horizon/), "12 months");
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    expect(await screen.findByText("Recent evidence supports a focused transformation pattern.")).toBeInTheDocument();
    expect(apiMock).toHaveBeenCalledWith({ organization: "BNY", question: "What changed recently?", time_horizon: "12 months" });
  });
});
