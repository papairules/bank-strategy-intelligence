import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StrategicSignalsPage } from "./StrategicSignalsPage";

const context = { total_jobs: 19, jobs_with_evidence: 19, hiring_evidence_coverage: 1, enriched_jobs: 1, enrichment_coverage: 1 / 19, hiring_signal_count: 3, technology_observation_count: 10, technology_signal_count: 0, observation_start: "2026-08-20", observation_end: "2026-08-21" };
function ok(body: unknown) { return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })); }
function renderPage() { return render(<MemoryRouter><StrategicSignalsPage /></MemoryRouter>); }
afterEach(() => vi.unstubAllGlobals());

describe("StrategicSignalsPage", () => {
  it("renders real coverage and a polished suppression state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => ok({ organization: "Wells Fargo", generated_at: "2026-08-21T12:00:00Z", generated_signal_count: 0, coverage_context: context, signals: [], limitations: ["Technology enrichment coverage is below the configured reliability threshold; broader cross-domain claims are withheld."] })));
    renderPage();
    expect(screen.getByText("Evaluating cross-domain evidence…")).toBeInTheDocument();
    expect(await screen.findByText("Insufficient cross-domain coverage for reliable strategic signals.")).toBeInTheDocument();
    expect(screen.getByText("5.3%")).toBeInTheDocument();
    expect(screen.getByText("Inspect supporting evidence")).toHaveAttribute("href", "/evidence");
  });

  it("renders populated scores, contributors, limitations, and traceability", async () => {
    const signal = { signal_id: "signal-1", organization: "Wells Fargo", signal_type: "capability_technology_alignment", title: "Observed overlap between analytics hiring and Python", summary: "Within the observed hiring evidence, analytics classifications overlap with Python observations across 3 independently contributing job records.", primary_subject: "Data & Analytics", related_subjects: ["Python"], domains_involved: ["hiring_intelligence", "technology_intelligence"], observation_start: "2026-07-01", observation_end: "2026-08-20", strength: 0.7, confidence: 0.75, evidence_coverage: 1, hiring_contributor_count: 4, technology_contributor_count: 3, unique_contributing_job_ids: ["job-1", "job-2", "job-3"], supporting_evidence_ids: ["e-1", "e-2", "e-3"], related_hiring_signal_ids: ["h-1"], related_technology_signal_ids: ["t-1"], limitations: ["Cross-domain overlap is observational."], provenance: { generator: "CrossDomainStrategicSignalService", configuration_version: "cross-domain-signals-v1", deterministic: true } };
    vi.stubGlobal("fetch", vi.fn(() => ok({ organization: "Wells Fargo", generated_at: "2026-08-21T12:00:00Z", generated_signal_count: 1, coverage_context: { ...context, enriched_jobs: 5, enrichment_coverage: 0.5, technology_signal_count: 1 }, signals: [signal], limitations: [] })));
    renderPage();
    expect(await screen.findByText(signal.title)).toBeInTheDocument();
    expect(screen.getByText("75% confidence")).toBeInTheDocument();
    expect(screen.getByText("4 hiring contributors")).toBeInTheDocument();
    expect(screen.getByText("3 technology contributors")).toBeInTheDocument();
    expect(screen.getByText("Trace evidence")).toHaveAttribute("href", "/evidence");
    expect(screen.getByText("Cross-domain overlap is observational.")).toBeInTheDocument();
  });

  it("renders a safe API error", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Backend unavailable"))));
    renderPage();
    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
  });
});
