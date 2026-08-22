import { postJson } from "./hiring";
import type { HiringAgentAnswer, HiringAgentAnswerRequest } from "../types/hiringAgent";

export const hiringAgentApi = {
  answer: (request: HiringAgentAnswerRequest, signal?: AbortSignal) =>
    postJson<HiringAgentAnswerRequest, HiringAgentAnswer>(
      "/api/v1/agents/hiring/answer",
      request,
      signal,
    ),
};
