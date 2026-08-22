import { postJson } from "./hiring";
import type { ReportQuestionAnswer, ReportQuestionRequest, SupervisorReportAnswer, SupervisorReportRequest } from "../types/supervisorReport";

export const supervisorReportApi = {
  generate: (request: SupervisorReportRequest, signal?: AbortSignal) =>
    postJson<SupervisorReportRequest, SupervisorReportAnswer>(
      "/api/v1/agents/supervisor/report",
      request,
      signal,
    ),
  answer: (request: ReportQuestionRequest, signal?: AbortSignal) =>
    postJson<ReportQuestionRequest, ReportQuestionAnswer>(
      "/api/v1/agents/supervisor/report/answer",
      request,
      signal,
    ),
};
