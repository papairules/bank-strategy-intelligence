import { postJson } from "./hiring";
import type {
  EvidenceAgentAnswer,
  EvidenceAgentAnswerRequest,
} from "../types/evidenceAgent";

export const evidenceAgentApi = {
  answer: (request: EvidenceAgentAnswerRequest, signal?: AbortSignal) =>
    postJson<EvidenceAgentAnswerRequest, EvidenceAgentAnswer>(
      "/api/v1/agents/evidence/answer",
      request,
      signal,
    ),
};
