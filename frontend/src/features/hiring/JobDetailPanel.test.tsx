import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobDetailPanel } from "./JobDetailPanel";
import { detailFixture } from "../../test/fixtures";

afterEach(() => vi.unstubAllGlobals());
const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));

describe("JobDetailPanel", () => {
  it("shows an explicit unavailable enrichment state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => ok(detailFixture)));
    render(<JobDetailPanel organization="Wells Fargo" jobId="job-1" onClose={() => undefined} />);
    expect(await screen.findByText("AI enrichment not yet available")).toBeInTheDocument();
    expect(screen.getByText("Senior Analytics Consultant")).toBeInTheDocument();
  });

  it("renders persisted enrichment and provenance", async () => {
    vi.stubGlobal("fetch", vi.fn(() => ok({ ...detailFixture, enrichment: { job_id: "job-1", evidence_id: "evidence-1", capability_classifications: ["Data & Analytics"], skills: ["Analytics"], technologies: ["Python"], seniority_level: "senior", is_leadership: false, business_unit: "Consumer Analytics", hiring_themes: ["data modernization"], confidence: 0.9, field_confidences: { technologies: 1 }, field_support: [], limitations: ["Evidence only."], model_metadata: { provider: "vertex_gemini", model: "gemini-2.5-flash", prompt_schema_version: "hiring-enrichment-v3", provider_request_id: null, model_version: null, usage_metadata: {}, enrichment_timestamp: "2026-08-21T12:00:00Z", model_confidence: 0.85 } } })));
    render(<JobDetailPanel organization="Wells Fargo" jobId="job-1" onClose={() => undefined} />);
    expect(await screen.findByText("Consumer Analytics")).toBeInTheDocument();
    expect(screen.getByText("gemini-2.5-flash")).toBeInTheDocument();
    expect(screen.getByText("Data & Analytics")).toBeInTheDocument();
  });
});
