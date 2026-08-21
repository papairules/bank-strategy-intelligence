import { describe, expect, it } from "vitest";
import { buildStrategicSignalsPath } from "./strategy";

describe("strategy API", () => {
  it("builds an encoded organization path", () => {
    expect(buildStrategicSignalsPath("Wells Fargo")).toBe(
      "/api/v1/strategy/organizations/Wells%20Fargo/signals",
    );
  });
});
