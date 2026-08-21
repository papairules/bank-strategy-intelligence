import { describe, expect, it } from "vitest";
import { buildEvidenceDetailPath, buildEvidenceRecordsPath } from "./evidence";

describe("evidence API", () => {
  it("builds encoded evidence filters and pagination", () => {
    const path = buildEvidenceRecordsPath("Wells Fargo", { search: "analytics role", source: "Workday", enriched: true, technology: "Power BI", capability: "Data & Analytics", location: "Charlotte, NC", limit: 20, offset: 40 });
    expect(path).toContain("/Wells%20Fargo/records?");
    expect(path).toContain("enriched=true");
    expect(path).toContain("technology=Power+BI");
    expect(path).toContain("capability=Data+%26+Analytics");
    expect(path).toContain("offset=40");
  });

  it("scopes direct evidence detail reads to the organization", () => {
    expect(buildEvidenceDetailPath("BNY", "evidence/123")).toBe(
      "/api/v1/evidence/evidence%2F123?organization=BNY",
    );
  });
});
