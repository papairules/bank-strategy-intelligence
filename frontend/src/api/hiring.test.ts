import { describe, expect, it } from "vitest";
import { buildJobDetailPath, buildJobsPath } from "./hiring";

describe("hiring API URL construction", () => {
  it("encodes organizations and server-side filters", () => {
    const path = buildJobsPath("Wells Fargo", {
      limit: 10,
      offset: 20,
      location: "New York",
      capability: "Data & Analytics",
      seniority: "senior",
    });
    expect(path).toContain("/organizations/Wells%20Fargo/jobs?");
    expect(path).toContain("limit=10");
    expect(path).toContain("offset=20");
    expect(path).toContain("location=New+York");
    expect(path).toContain("capability=Data+%26+Analytics");
    expect(path).toContain("seniority=senior");
  });

  it("scopes direct job detail reads to the organization", () => {
    expect(buildJobDetailPath("Goldman Sachs", "job/123")).toBe(
      "/api/v1/hiring/jobs/job%2F123?organization=Goldman+Sachs",
    );
  });
});
