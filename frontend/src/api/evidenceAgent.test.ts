import { afterEach, describe, expect, it, vi } from "vitest";
import { evidenceAgentApi } from "./evidenceAgent";

describe("evidenceAgentApi", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("posts only organization and question to the governed endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: "answered" }) });
    vi.stubGlobal("fetch", fetchMock);
    await evidenceAgentApi.answer({ organization: "Wells Fargo", question: "What is supported?" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/agents/evidence/answer",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ organization: "Wells Fargo", question: "What is supported?" }),
      }),
    );
  });
});
