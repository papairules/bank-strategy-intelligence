import { afterEach, describe, expect, it, vi } from "vitest";
import { strategyAgentApi } from "./strategyAgent";

afterEach(() => vi.unstubAllGlobals());

describe("strategyAgentApi", () => {
  it("posts only the approved request contract", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ status: "insufficient_evidence" }), { status: 200, headers: { "Content-Type": "application/json" } })));
    vi.stubGlobal("fetch", fetchMock);
    await strategyAgentApi.answer({ organization: "Wells Fargo", question: "What is supported?" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/api/v1/agents/strategy/answer");
    expect(JSON.parse(options.body as string)).toEqual({ organization: "Wells Fargo", question: "What is supported?" });
  });
});
