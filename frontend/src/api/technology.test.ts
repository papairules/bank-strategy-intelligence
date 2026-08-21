import { describe, expect, it } from "vitest";
import { buildTechnologyObservationsPath } from "./technology";

describe("technology API", () => {
  it("builds encoded pagination and filter queries", () => {
    const path = buildTechnologyObservationsPath("Wells Fargo", {
      technology: "Power BI",
      category: "BI / Visualization",
      businessUnit: "Consumer Analytics",
      location: "Charlotte, NC",
      limit: 20,
      offset: 40,
    });
    expect(path).toContain("/Wells%20Fargo/observations?");
    expect(path).toContain("technology=Power+BI");
    expect(path).toContain("category=BI+%2F+Visualization");
    expect(path).toContain("limit=20");
    expect(path).toContain("offset=40");
  });
});
