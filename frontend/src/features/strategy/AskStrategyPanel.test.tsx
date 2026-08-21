import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/hiring";
import { strategyAgentApi } from "../../api/strategyAgent";
import type { StrategyAgentAnswer } from "../../types/strategyAgent";
import { AskStrategyPanel } from "./AskStrategyPanel";

vi.mock("../../api/strategyAgent", () => ({ strategyAgentApi: { answer: vi.fn() } }));

const answer: StrategyAgentAnswer = {
  status: "answered", organization: "Wells Fargo", question: "What is supported?",
  executive_summary: "The available evidence suggests a limited observed analytics pattern.",
  findings: [{ title: "Observed analytics demand", statement: "Analytics demand appears in the observed sample.", support: [
    { reference: "strategy_ref_1", domain: "hiring", support_class: "source_evidence", tool_name: "evidence.search", evidence_ids: ["evidence-1"], job_ids: ["job-1"], signal_ids: [] },
    { reference: "strategy_ref_2", domain: "technology", support_class: "ai_enrichment", tool_name: "technology.search_observations", evidence_ids: [], job_ids: [], signal_ids: [] },
    { reference: "strategy_ref_3", domain: "technology", support_class: "derived_analytics", tool_name: "technology.get_analytics", evidence_ids: [], job_ids: [], signal_ids: [] },
    { reference: "strategy_ref_4", domain: "strategy", support_class: "derived_signal", tool_name: "strategy.get_signals", evidence_ids: [], job_ids: [], signal_ids: [] },
  ] }], reliability: .42, limitations: ["The observation period is short."], tool_calls_used: 4,
  provider: "vertex_gemini", model: "gemini-2.5-flash", agent_version: "strategy-orchestrator-v1",
};
const apiMock = vi.mocked(strategyAgentApi.answer);

afterEach(() => { cleanup(); vi.clearAllMocks(); });
function renderPanel() { return render(<MemoryRouter><AskStrategyPanel organization="Wells Fargo" /></MemoryRouter>); }
async function submit() { const user = userEvent.setup(); await user.type(screen.getByLabelText("Strategic question"), "What is supported?"); await user.click(screen.getByRole("button", { name: "Analyze" })); return user; }

describe("AskStrategyPanel", () => {
  it("is idle and never requests on page load", () => {
    renderPanel();
    expect(screen.getByText(/No Strategy Agent request is made/)).toBeInTheDocument();
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("renders answered synthesis, findings, support classes, reliability, limitations, and evidence navigation", async () => {
    apiMock.mockResolvedValue(answer); renderPanel(); await submit();
    expect(await screen.findByText(answer.executive_summary)).toBeInTheDocument();
    expect(screen.getByText("Observed analytics demand")).toBeInTheDocument();
    expect(screen.getByText("Source Evidence")).toBeInTheDocument();
    expect(screen.getByText("AI Enrichment")).toBeInTheDocument();
    expect(screen.getByText("Derived Analytics")).toBeInTheDocument();
    expect(screen.getByText("Derived Signal")).toBeInTheDocument();
    expect(screen.getByText("42.0%")).toBeInTheDocument();
    expect(screen.getByText(/not a probability/)).toBeInTheDocument();
    expect(screen.getByText(answer.limitations[0])).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View supporting evidence" })).toHaveAttribute("href", "/evidence");
  });

  it("treats insufficient evidence as a governed success", async () => {
    apiMock.mockResolvedValue({ ...answer, status: "insufficient_evidence", findings: [], reliability: 0 }); renderPanel(); await submit();
    expect(await screen.findByText(/insufficient to support a reliable organization-wide/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([["disabled_agent", "Strategy Agent unavailable"], ["provider_unavailable", "Provider temporarily unavailable"], ["claim_validation", "Governed synthesis unavailable"]])("renders safe %s failures", async (code, title) => {
    apiMock.mockRejectedValue(new ApiError("Safe failure", 503, code)); renderPanel(); await submit();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(/No automatic retry/)).toBeInTheDocument();
  });

  it("shows loading and prevents duplicate submission", async () => {
    let resolve!: (value: StrategyAgentAnswer) => void;
    apiMock.mockReturnValue(new Promise((done) => { resolve = done; })); renderPanel(); const user = await submit();
    expect(screen.getByRole("status")).toHaveTextContent("Reviewing approved intelligence sources");
    const button = screen.getByRole("button", { name: "Analyzing intelligence…" });
    expect(button).toBeDisabled(); await user.click(button); expect(apiMock).toHaveBeenCalledTimes(1);
    resolve(answer); await waitFor(() => expect(screen.getByText(answer.executive_summary)).toBeInTheDocument());
  });
});
