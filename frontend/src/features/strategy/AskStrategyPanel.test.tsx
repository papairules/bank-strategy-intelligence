import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/hiring";
import { strategyAgentApi } from "../../api/strategyAgent";
import type { StrategyAgentAnswer, StrategyEvidence } from "../../types/strategyAgent";
import { AskStrategyPanel } from "./AskStrategyPanel";

vi.mock("../../api/strategyAgent", () => ({ strategyAgentApi: { answer: vi.fn() } }));

function evidence(id: string, theme: string, url: string): StrategyEvidence {
  return {
    evidence_id: id, theme, business_unit: null, signal_type: "TRANSFORMATION", direction: "modernize",
    statement: `${theme} supporting statement.`, time_horizon: "Next 12 months", source_id: `source-${id}`,
    source_url: url, source_type: "company_announcement", publication_date: "2026-01-10",
  };
}

const answer: StrategyAgentAnswer = {
  status: "answered", organization: "Wells Fargo", question: "What is supported?",
  executive_summary: "Evidence-backed research identified two supported strategic themes.",
  findings: [{ title: "Duplicate finding", statement: "This must not render separately.", support: [] }],
  reliability: .42, limitations: ["The observation period is short."], tool_calls_used: 4,
  provider: "openai", model: "gpt-5.4-mini", agent_version: "strategy-orchestrator-v1",
  strategic_signals: [
    {
      priority: "Risk and control infrastructure", business_unit: "Risk", direction: "transform", time_horizon: "Next 12 months",
      hypothesis: "The company is continuing to transform risk and control infrastructure.", supporting_evidence_ids: ["EV_005", "EV_006"],
      confidence: .85, confidence_breakdown: { source_quality: .85 }, evidence: [
        evidence("EV_005", "Risk infrastructure", "https://example.com/risk"),
        evidence("EV_006", "Duplicate risk source", "https://example.com/risk"),
      ],
    },
    {
      priority: "Operating efficiency", business_unit: null, direction: "optimize", time_horizon: "Next 12 months",
      hypothesis: "The company is continuing to optimize operating efficiency.", supporting_evidence_ids: ["EV_008", "EV_009"],
      confidence: .75, confidence_breakdown: { source_quality: .75 }, evidence: [
        evidence("EV_008", "Process simplification", "https://example.com/process"),
        evidence("EV_009", "Automation", "https://example.com/automation"),
      ],
    },
  ],
};

const apiMock = vi.mocked(strategyAgentApi.answer);

beforeEach(() => window.sessionStorage.clear());
afterEach(() => { cleanup(); vi.clearAllMocks(); });

function renderPanel(organization = "Wells Fargo") {
  return render(<MemoryRouter><AskStrategyPanel organization={organization} /></MemoryRouter>);
}

async function submit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Strategic question"), "What is supported?");
  await user.click(screen.getByRole("button", { name: "Analyze" }));
  return user;
}

describe("AskStrategyPanel", () => {
  it("is idle and never requests on page load", () => {
    renderPanel();
    expect(screen.getByText(/No Strategy Agent request is made/)).toBeInTheDocument();
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("renders compact themes without confidence, IDs, duplicate sections, or implementation metadata", async () => {
    apiMock.mockResolvedValue(answer);
    renderPanel();
    await submit();

    expect(await screen.findByText(answer.executive_summary)).toBeInTheDocument();
    expect(screen.getByText("Strategy analysis")).toBeInTheDocument();
    expect(screen.getByText("Strategic themes")).toBeInTheDocument();
    expect(screen.getByText("Risk and control infrastructure")).toBeInTheDocument();
    expect(screen.getByText("The company is continuing to transform risk and control infrastructure.")).toBeInTheDocument();
    expect(screen.getAllByText("Next 12 months")).toHaveLength(2);
    expect(screen.queryByText("85.0%")).not.toBeInTheDocument();
    expect(screen.queryByText(/EV_00/)).not.toBeInTheDocument();
    expect(screen.queryByText("Findings")).not.toBeInTheDocument();
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
    expect(screen.queryByText("Duplicate finding")).not.toBeInTheDocument();
    expect(screen.queryByText("gpt-5.4-mini")).not.toBeInTheDocument();
    expect(screen.queryByText("Application validated")).not.toBeInTheDocument();
    expect(screen.queryByText("42.0%")).not.toBeInTheDocument();
  });

  it("deduplicates URLs within each theme and expands source groups independently", async () => {
    apiMock.mockResolvedValue(answer);
    renderPanel();
    const user = await submit();
    await screen.findByText("Risk and control infrastructure");

    const riskCard = screen.getByText("Risk and control infrastructure").closest("article")!;
    const efficiencyCard = screen.getByText("Operating efficiency").closest("article")!;
    const riskDetails = riskCard.querySelector("details")!;
    const efficiencyDetails = efficiencyCard.querySelector("details")!;
    expect(within(riskCard).getByText("1 source")).toBeInTheDocument();
    expect(within(efficiencyCard).getByText("2 sources")).toBeInTheDocument();
    expect(riskDetails).not.toHaveAttribute("open");
    expect(efficiencyDetails).not.toHaveAttribute("open");

    await user.click(within(efficiencyCard).getByText("2 sources"));
    expect(efficiencyDetails).toHaveAttribute("open");
    expect(riskDetails).not.toHaveAttribute("open");
    expect(within(efficiencyCard).getAllByRole("link", { name: "Open source ↗" })).toHaveLength(2);
    expect(within(efficiencyCard).getAllByRole("link", { name: "Open source ↗" })[0]).toHaveAttribute("href", "https://example.com/process");
  });

  it("submits the selected organization and optional time horizon unchanged", async () => {
    apiMock.mockResolvedValue({ ...answer, organization: "BNY" });
    renderPanel("BNY");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Strategic question"), "What is supported?");
    await user.type(screen.getByLabelText(/Time horizon/), "2025–2027");
    await user.click(screen.getByRole("button", { name: "Analyze" }));
    await screen.findByText(answer.executive_summary);
    expect(apiMock).toHaveBeenCalledWith({ organization: "BNY", question: "What is supported?", time_horizon: "2025–2027" });
  });

  it("treats insufficient evidence as a governed success", async () => {
    apiMock.mockResolvedValue({ ...answer, status: "insufficient_evidence", strategic_signals: [] });
    renderPanel();
    await submit();
    expect(await screen.findByText(/insufficient to support a reliable organization-wide/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([["disabled_agent", "Strategy Agent unavailable"], ["provider_unavailable", "Provider temporarily unavailable"], ["claim_validation", "Governed synthesis unavailable"]])("renders safe %s failures", async (code, title) => {
    apiMock.mockRejectedValue(new ApiError("Safe failure", 503, code));
    renderPanel();
    await submit();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(/No automatic retry/)).toBeInTheDocument();
  });

  it("renders an organization scope mismatch clearly", async () => {
    apiMock.mockRejectedValue(new ApiError(
      "The question targets Goldman Sachs, but the current data scope is Wells Fargo. Switch the Current Data Scope to Goldman Sachs or ask about Wells Fargo.",
      422,
      "organization_scope_mismatch",
    ));
    renderPanel();
    await submit();
    expect(await screen.findByText("Organization scope mismatch")).toBeInTheDocument();
    expect(screen.getByText(/current data scope is Wells Fargo/)).toBeInTheDocument();
  });

  it("shows loading and prevents duplicate submission", async () => {
    let resolve!: (value: StrategyAgentAnswer) => void;
    apiMock.mockReturnValue(new Promise((done) => { resolve = done; }));
    renderPanel();
    const user = await submit();
    expect(screen.getByRole("status")).toHaveTextContent("Reviewing approved intelligence sources");
    const button = screen.getByRole("button", { name: "Analyzing intelligence…" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(apiMock).toHaveBeenCalledTimes(1);
    resolve(answer);
    await waitFor(() => expect(screen.getByText(answer.executive_summary)).toBeInTheDocument());
  });
});
