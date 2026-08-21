import { postJson } from "./hiring";
import type { StrategyAgentAnswer, StrategyAgentAnswerRequest } from "../types/strategyAgent";

export const strategyAgentApi = {
  answer: (request: StrategyAgentAnswerRequest, signal?: AbortSignal) =>
    postJson<StrategyAgentAnswerRequest, StrategyAgentAnswer>(
      "/api/v1/agents/strategy/answer",
      request,
      signal,
    ),
};
