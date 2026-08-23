import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/hiring";
import { evidenceAgentApi } from "../../api/evidenceAgent";
import type { EvidenceAgentAnswer } from "../../types/evidenceAgent";
import { AskEvidencePanel } from "./AskEvidencePanel";

vi.mock("../../api/evidenceAgent", () => ({ evidenceAgentApi: { answer: vi.fn() } }));

const answer: EvidenceAgentAnswer = {
  status: "answered",
  organization: "Wells Fargo",
  question: "What technologies are supported?",
  answer: "SQL and Python are supported by the available enrichment.",
  citations: [{ evidence_id: "evidence-1", job_id: "job-1", relationship_type: "hiring_enrichment", source_type: "career_site", excerpt: null }],
  evidence_records_considered: 1,
  tool_calls_used: 1,
  reliability: 0.4111,
  limitations: ["Hiring evidence does not establish corporate intent."],
  provider: "vertex_gemini",
  model: "gemini-2.5-flash",
  agent_version: "evidence-agent-v1",
};

const apiMock = vi.mocked(evidenceAgentApi.answer);

beforeEach(() => window.sessionStorage.clear());
afterEach(() => { cleanup(); vi.clearAllMocks(); });

async function submit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Question"), "What technologies are supported?");
  await user.click(screen.getByRole("button", { name: "Ask Evidence" }));
  return user;
}

describe("AskEvidencePanel", () => {
  it("is idle and makes no request before explicit submission", () => {
    render(<AskEvidencePanel organization="Wells Fargo" onViewEvidence={vi.fn()} />);
    expect(screen.getByText(/No agent request is made/)).toBeInTheDocument();
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("renders a successful answer, reliability, citation, provenance, and navigation", async () => {
    apiMock.mockResolvedValue(answer);
    const onViewEvidence = vi.fn();
    render(<AskEvidencePanel organization="Wells Fargo" onViewEvidence={onViewEvidence} />);
    const user = await submit();
    expect(await screen.findByText(answer.answer)).toBeInTheDocument();
    expect(screen.getByText("41.1%")).toBeInTheDocument();
    expect(screen.getByText("AI enrichment")).toBeInTheDocument();
    expect(screen.getByText("gemini-2.5-flash")).toBeInTheDocument();
    expect(screen.getByText(answer.limitations[0])).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "View Evidence" }));
    expect(onViewEvidence).toHaveBeenCalledWith("evidence-1");
  });

  it("renders insufficient evidence honestly", async () => {
    apiMock.mockResolvedValue({ ...answer, status: "insufficient_evidence", answer: "The available evidence is insufficient.", citations: [] });
    render(<AskEvidencePanel organization="Wells Fargo" onViewEvidence={vi.fn()} />);
    await submit();
    expect(await screen.findByText(/does not support a broader answer/)).toBeInTheDocument();
    expect(screen.getByText(/No citation met/)).toBeInTheDocument();
  });

  it.each([
    ["disabled_agent", "Evidence Agent unavailable"],
    ["provider_unavailable", "Provider temporarily unavailable"],
    ["citation_validation", "Grounded answer unavailable"],
  ])("renders safe %s failures", async (code, title) => {
    apiMock.mockRejectedValue(new ApiError("Safe failure", 503, code));
    render(<AskEvidencePanel organization="Wells Fargo" onViewEvidence={vi.fn()} />);
    await submit();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(/No automatic retry/)).toBeInTheDocument();
  });

  it("shows loading and prevents duplicate submission", async () => {
    let resolve!: (value: EvidenceAgentAnswer) => void;
    apiMock.mockReturnValue(new Promise((done) => { resolve = done; }));
    render(<AskEvidencePanel organization="Wells Fargo" onViewEvidence={vi.fn()} />);
    const user = await submit();
    expect(screen.getByRole("status")).toHaveTextContent("Reviewing approved evidence sources");
    const button = screen.getByRole("button", { name: "Analyzing evidence…" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(apiMock).toHaveBeenCalledTimes(1);
    resolve(answer);
    await waitFor(() => expect(screen.getByText(answer.answer)).toBeInTheDocument());
  });
});
