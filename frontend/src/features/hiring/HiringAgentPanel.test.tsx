import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/hiring";
import { hiringAgentApi } from "../../api/hiringAgent";
import type { HiringAgentAnswer } from "../../types/hiringAgent";
import { HiringAgentPanel } from "./HiringAgentPanel";

vi.mock("../../api/hiringAgent", () => ({ hiringAgentApi: { answer: vi.fn() } }));

const answer: HiringAgentAnswer = {
  status: "analyzed",
  organization: "Wells Fargo",
  generated_at: "2026-08-22T00:00:00+00:00",
  total_input_jobs: 4,
  unique_jobs: 4,
  enriched_jobs: 4,
  failed_enrichments: 0,
  hiring_signals: [{
    company_id: "WELLS_FARGO", business_unit: "Corporate and Investment Banking", department: null,
    capability: "Cloud and Platform Engineering", direction: "concentration", strength: 0.6, job_count: 4,
    previous_job_count: null, senior_role_count: 1, related_skills: ["Kubernetes"], related_technologies: ["AWS"],
    supporting_job_ids: ["REQ1"], evidence_date: "2026-08-21", analysis_period: "current active-job snapshot",
    confidence: 0.5, confidence_breakdown: { classification: 0.2 },
  }],
  evidence: [{
    evidence_id: "HIRE_EV_00001", company_id: "WELLS_FARGO", source_job_id: "REQ1", job_title: "Senior Cloud Engineer",
    business_unit: "Corporate and Investment Banking", capability: "Cloud and Platform Engineering",
    location: "New York, NY, US", posting_date: "2026-08-01", source_url: "https://example.com/jobs/REQ1",
    statement: "Open role: Senior Cloud Engineer; capability: Cloud and Platform Engineering",
  }],
  warnings: [],
  provider: "openai",
  model: "gpt-5.4-mini",
  agent_version: "hiring-agent-v1",
};
const apiMock = vi.mocked(hiringAgentApi.answer);

beforeEach(() => window.sessionStorage.clear());
afterEach(() => { cleanup(); vi.clearAllMocks(); });
function renderPanel() { return render(<HiringAgentPanel organization="Wells Fargo" />); }
async function run() { const user = userEvent.setup(); await user.click(screen.getByRole("button", { name: "Run analysis" })); return user; }

describe("HiringAgentPanel", () => {
  it("is idle and never requests on page load", () => {
    renderPanel();
    expect(screen.getByText(/No Hiring Agent request is made/)).toBeInTheDocument();
    expect(apiMock).not.toHaveBeenCalled();
  });

  it("renders analyzed capability signals", async () => {
    apiMock.mockResolvedValue(answer);
    renderPanel();
    await run();
    expect(await screen.findByText("Cloud and Platform Engineering")).toBeInTheDocument();
    expect(screen.getByText("Corporate and Investment Banking")).toBeInTheDocument();
    expect(screen.getByText("4 jobs")).toBeInTheDocument();
    expect(apiMock).toHaveBeenCalledWith({ organization: "Wells Fargo" });
  });

  it("treats insufficient data as a governed success", async () => {
    apiMock.mockResolvedValue({ ...answer, status: "insufficient_data", hiring_signals: [], evidence: [], warnings: ["No persisted jobs are available for this organization yet."] });
    renderPanel();
    await run();
    expect(await screen.findByText(/Run a hiring collection first/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders a safe disabled-agent failure", async () => {
    apiMock.mockRejectedValue(new ApiError("Safe failure", 503, "disabled_agent"));
    renderPanel();
    await run();
    expect(await screen.findByText("Hiring Agent unavailable")).toBeInTheDocument();
    expect(screen.getByText(/No automatic retry/)).toBeInTheDocument();
  });

  it("disables the button while submitting", async () => {
    let resolve!: (value: HiringAgentAnswer) => void;
    apiMock.mockReturnValue(new Promise((done) => { resolve = done; }));
    renderPanel();
    const user = await run();
    const button = screen.getByRole("button", { name: "Analyzing hiring data…" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(apiMock).toHaveBeenCalledTimes(1);
    resolve(answer);
    expect(await screen.findByText("Cloud and Platform Engineering")).toBeInTheDocument();
  });
});
