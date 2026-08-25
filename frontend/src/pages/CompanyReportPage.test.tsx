import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { OrganizationProvider } from "../context/OrganizationContext";
import type { ReportReference } from "../types/supervisorReport";
import { CompanyReportPage } from "./CompanyReportPage";

const references: ReportReference[] = Array.from({ length: 9 }, (_, index) => ({ reference_id: `source-${index}`, domain: "strategy", evidence_ids: [`EV_00${index}`], job_ids: [], source_url: index === 0 ? "https://wellsfargo.com/annual-report" : `https://sec.gov/report-${index}` }));
references.push({ ...references[0], reference_id: "duplicate-url" });
references.push(
  { reference_id: "strategy-internal", domain: "strategy", evidence_ids: ["EV_INTERNAL"], job_ids: [], source_url: null },
  { reference_id: "hiring-signal", domain: "hiring", evidence_ids: ["HIRING_1"], job_ids: [], source_url: null },
  { reference_id: "hiring-external", domain: "hiring", evidence_ids: ["HIRING_2"], job_ids: [], source_url: "https://jobs.example.com/job-1" },
  { reference_id: "kg:technology:python", domain: "hiring_kg", evidence_ids: ["KG_1"], job_ids: ["job-1"], source_url: null },
);

function lobRow(overrides = {}) { return {
  line_of_business: "Commercial Banking", emerging_ai_theme: "Agentic underwriting", likely_use_cases: ["Credit memo generation", "Covenant analysis"],
  signal_strength: "Very High", relevant_hiring_jobs: 1203, narrative: "Wells Fargo's recent 10-Q highlights continued investment in commercial underwriting automation, and the hiring profile shows a matching concentration of underwriting-adjacent roles.",
  supporting_reference_ids: ["source-8"], ...overrides,
}; }

function response(lobRows = [lobRow(), lobRow({ line_of_business: "Wealth and Investment Management", emerging_ai_theme: "Advisor copilot", likely_use_cases: ["Meeting prep"], signal_strength: "Medium", relevant_hiring_jobs: null })]) { return {
  organization: "Goldman Sachs", strategy_signal_count: 2, hiring_signal_count: 3,
  coverage: { total_jobs: 847, enriched_jobs: 0, enrichment_coverage_percentage: 0, kg_enriched_job_count: 0, limitations: [] },
  report: {
    organization: "Goldman Sachs", total_hiring_jobs: 847, executive_summary: "Evidence suggests focused modernization.", strategic_priorities: [], hiring_intelligence: [], cross_domain_alignment: [{ title: "Alignment", narrative: "Strategy and hiring align.", supporting_reference_ids: ["source-8"] }], business_areas_to_watch: [],
    lob_opportunities: lobRows, evidence_traceability: references, limitations: ["Hiring concentration is not proof of strategic investment."],
  }, provider: "openai", model: "test-model",
}; }

const qaResponse = {
  organization: "Goldman Sachs", question: "Where do strategy and hiring align?", answer: "The report shows alignment around modernization.", evidence_sufficient: true,
  supporting_references: [{ reference_id: "source-0", reference_type: "strategy_source", label: "source0", source_url: "https://source0.example.com/report", hiring_job_count: null }],
  limitations: ["Alignment does not prove causation."], provider: "openai", model: "test-model",
};

function setup(payload = response(), qaPayload: object = qaResponse, qaStatus = 200) {
  const fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    void init;
    if (String(input).endsWith("/supervisor/report/answer")) {
      return Promise.resolve(new Response(JSON.stringify(qaPayload), { status: qaStatus, headers: { "Content-Type": "application/json" } }));
    }
    return Promise.resolve(new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }));
  });
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><OrganizationProvider value={{ organization: "Goldman Sachs", setOrganization: vi.fn() }}><CompanyReportPage /></OrganizationProvider></MemoryRouter>);
  return fetch;
}

beforeEach(() => window.sessionStorage.clear());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("renders the API-backed LOB opportunity table with five columns and an expandable narrative", async () => {
  const fetch = setup();
  expect(await screen.findByText("Evidence suggests focused modernization.")).toBeInTheDocument();
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ organization: "Goldman Sachs" });
  expect(screen.getByText("Goldman Sachs", { selector: ".report-company-summary strong" })).toBeInTheDocument();
  expect(screen.getByText(/847 Total Hiring Jobs/)).toBeInTheDocument();

  const outlook = screen.getByText("AI Opportunity by Line of Business").closest("section")!;
  const headings = within(outlook).getAllByRole("columnheader");
  expect(headings.map((item) => item.textContent)).toEqual(["Line of Business", "Emerging AI Theme", "Likely High-Value Use Cases", "Signal Strength", "Relevant Hiring Jobs"]);
  expect(within(outlook).getByText("Commercial Banking")).toBeInTheDocument();
  expect(within(outlook).getByText("Wealth and Investment Management")).toBeInTheDocument();
  expect(within(outlook).getByText("Agentic underwriting")).toBeInTheDocument();
  expect(within(outlook).getByText("Credit memo generation, Covenant analysis")).toBeInTheDocument();
  expect(within(outlook).getByText("Very High")).toBeInTheDocument();
  expect(within(outlook).getByText("1,203")).toBeInTheDocument();
  expect(within(outlook).getByText("—")).toBeInTheDocument();

  expect(within(outlook).queryByText(/recent 10-Q highlights/)).not.toBeInTheDocument();
  await userEvent.click(within(outlook).getByText("Commercial Banking"));
  expect(within(outlook).getByText(/recent 10-Q highlights/)).toBeInTheDocument();
  await userEvent.click(within(outlook).getByText("Commercial Banking"));
  expect(within(outlook).queryByText(/recent 10-Q highlights/)).not.toBeInTheDocument();

  // No separate ranked summary table -- the primary table is already ordered by signal strength.
  expect(screen.queryByText("Consolidated View")).not.toBeInTheDocument();
});

it("regenerates the report with a refined focus question on demand", async () => {
  const fetch = setup();
  await screen.findByText("Evidence suggests focused modernization.");
  expect(fetch).toHaveBeenCalledTimes(1);

  await userEvent.type(screen.getByLabelText(/Refine report focus/), "Where should we focus first?");
  await userEvent.click(screen.getByRole("button", { name: "Regenerate with this focus" }));
  await screen.findByText("Evidence suggests focused modernization.");

  expect(fetch).toHaveBeenCalledTimes(2);
  expect(JSON.parse(String(fetch.mock.calls[1][1]?.body))).toEqual({ organization: "Goldman Sachs", question: "Where should we focus first?" });
});

it("shows the LOB opportunity empty state", async () => {
  setup(response([]));
  expect(await screen.findByText("No supported AI opportunities are available for this report.")).toBeInTheDocument();
});

it("keeps report sources collapsed, deduplicates exact URLs, and preserves distinct same-domain documents", async () => {
  setup();
  const details = (await screen.findByText("9 report sources")).closest("details")!;
  expect(details).not.toHaveAttribute("open");
  await userEvent.click(within(details).getByText("9 report sources"));
  expect(details).toHaveAttribute("open");
  const links = within(details).getAllByRole("link", { name: "Open source ↗" });
  expect(links).toHaveLength(9);
  expect(links[0]).toHaveAttribute("href", "https://wellsfargo.com/annual-report");
  expect(links[1]).toHaveAttribute("href", "https://sec.gov/report-1");
  expect(screen.queryByText(/EV_00/)).not.toBeInTheDocument();
  expect(within(details).queryByText("Strategy · Internal evidence")).not.toBeInTheDocument();
  expect(within(details).queryByText("Hiring External")).not.toBeInTheDocument();
});

it("keeps methodology limitations available but collapsed by default", async () => {
  setup();
  const details = (await screen.findByText("Methodology & Limitations")).closest("details")!;
  expect(details).not.toHaveAttribute("open");
  expect(within(details).getByText("Hiring concentration is not proof of strategic investment.")).toBeInTheDocument();
});

it("groups grounded report Q&A references without changing the answer or request", async () => {
  const qaWithReferences = { ...qaResponse, supporting_references: [
    { reference_id: "source-0", reference_type: "strategy_source", label: "EV_005", source_url: "https://sec.gov/report-0", hiring_job_count: null },
    { reference_id: "source-duplicate", reference_type: "strategy_source", label: "Duplicate", source_url: "https://sec.gov/report-0", hiring_job_count: null },
    { reference_id: "source-1", reference_type: "strategy_source", label: "Annual Report", source_url: "https://sec.gov/report-1", hiring_job_count: null },
    { reference_id: "opportunity-1", reference_type: "opportunity", label: "AI Enablement & Modernization", source_url: null, hiring_job_count: 1203 },
    { reference_id: "hiring-1", reference_type: "hiring_evidence", label: "Persisted Hiring Intelligence", source_url: null, hiring_job_count: null },
    { reference_id: "hiring-2", reference_type: "hiring_evidence", label: "Persisted Hiring Intelligence", source_url: null, hiring_job_count: null },
    { reference_id: "hiring-2", reference_type: "hiring_evidence", label: "Persisted Hiring Intelligence", source_url: null, hiring_job_count: null },
    { reference_id: "strategy-1", reference_type: "report_evidence", label: "strategy", source_url: null, hiring_job_count: null },
    { reference_id: "strategy-2", reference_type: "strategy_evidence", label: "Report Evidence", source_url: null, hiring_job_count: null },
    { reference_id: "kg-internal-1", reference_type: "kg_evidence", label: "kg:technology:python", source_url: null, hiring_job_count: null },
  ] };
  const fetch = setup(response(), qaWithReferences);
  expect(await screen.findByText("Ask about this report")).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Ask a follow-up question about this report"), "Where do strategy and hiring align?");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByText("The report shows alignment around modernization.")).toBeInTheDocument();
  const answerText = await screen.findByText("The report shows alignment around modernization.");
  expect(answerText).toHaveClass("report-qa__answer-text");
  const details = screen.getByText("8 supporting references").closest("details")!;
  expect(details).not.toHaveAttribute("open");
  await userEvent.click(within(details).getByText("8 supporting references"));
  expect(details).toHaveAttribute("open");
  expect(within(details).getByRole("heading", { name: "External Sources" })).toBeInTheDocument();
  expect(within(details).getByRole("heading", { name: "Report Opportunities" })).toBeInTheDocument();
  expect(within(details).getByRole("heading", { name: "Internal Hiring Evidence" })).toBeInTheDocument();
  expect(within(details).getByRole("heading", { name: "Report Evidence" })).toBeInTheDocument();
  expect(within(details).getByRole("heading", { name: "Other Supporting Evidence" })).toBeInTheDocument();
  expect(within(details).getAllByRole("link", { name: "Open source ↗" })).toHaveLength(2);
  expect(within(details).getAllByText("sec.gov")).toHaveLength(2);
  expect(within(details).getByText("Annual Report")).toBeInTheDocument();
  expect(within(details).getByText("AI Enablement & Modernization")).toBeInTheDocument();
  expect(within(details).getByText("1,203 relevant jobs")).toBeInTheDocument();
  expect(within(details).getByText("Hiring Intelligence")).toBeInTheDocument();
  expect(within(details).getAllByText("2 supporting references")).toHaveLength(2);
  expect(within(details).getByText("Strategy report evidence")).toBeInTheDocument();
  expect(within(details).queryByText("Persisted Hiring Intelligence")).not.toBeInTheDocument();
  expect(within(details).queryByText("strategy")).not.toBeInTheDocument();
  expect(screen.queryByText("EV_005")).not.toBeInTheDocument();
  expect(screen.queryByText("kg:technology:python")).not.toBeInTheDocument();
  expect(within(details).queryByText("Duplicate")).not.toBeInTheDocument();
  const request = JSON.parse(String(fetch.mock.calls[1][1]?.body));
  expect(request.organization).toBe("Goldman Sachs");
  expect(request.report.total_hiring_jobs).toBe(847);
  expect(request.report.lob_opportunities[0].relevant_hiring_jobs).toBe(1203);
  expect(request.report.evidence_traceability.some((item: { reference_id: string }) => item.reference_id === "source-8")).toBe(true);
  expect(request.report).not.toHaveProperty("hiring_intelligence");
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("submits suggested questions and displays insufficient evidence", async () => {
  setup(response(), { ...qaResponse, answer: "The current report does not contain enough evidence.", evidence_sufficient: false, supporting_references: [] });
  await userEvent.click(await screen.findByRole("button", { name: "What should we prioritize in the next 90 days?" }));
  expect(await screen.findByText("The current report does not contain enough evidence.")).toBeInTheDocument();
  expect(screen.getByText("The current report does not contain enough evidence for a fully supported answer.")).toBeInTheDocument();
  expect(screen.getByLabelText("Ask a follow-up question about this report")).toHaveValue("What should we prioritize in the next 90 days?");
});

it("renders a safe report Q&A API error", async () => {
  setup(response(), { detail: { code: "provider_unavailable", message: "Report Q&A is temporarily unavailable." } }, 503);
  await userEvent.type(await screen.findByLabelText("Ask a follow-up question about this report"), "What are the top opportunities?");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Report Q&A is temporarily unavailable.");
});

it("shows the report Q&A loading state", async () => {
  let resolveAnswer: ((value: Response) => void) | undefined;
  const fetch = vi.fn((input: RequestInfo | URL) => {
    if (String(input).endsWith("/supervisor/report/answer")) {
      return new Promise<Response>((resolve) => { resolveAnswer = resolve; });
    }
    return Promise.resolve(new Response(JSON.stringify(response()), { status: 200, headers: { "Content-Type": "application/json" } }));
  });
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><OrganizationProvider value={{ organization: "Goldman Sachs", setOrganization: vi.fn() }}><CompanyReportPage /></OrganizationProvider></MemoryRouter>);
  await userEvent.type(await screen.findByLabelText("Ask a follow-up question about this report"), "Where should we focus first?");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(screen.getByRole("status")).toHaveTextContent("Reviewing report evidence");
  resolveAnswer?.(new Response(JSON.stringify(qaResponse), { status: 200, headers: { "Content-Type": "application/json" } }));
  expect(await screen.findByText("The report shows alignment around modernization.")).toBeInTheDocument();
});
