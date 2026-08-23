import { getJson } from "./hiring";
import type { GraphInsightsSnapshot } from "../types/graphInsights";

export const graphInsightsApi = {
  get: (organization: string, signal?: AbortSignal) =>
    getJson<GraphInsightsSnapshot>(
      `/api/v1/graph-insights/organizations/${encodeURIComponent(organization)}`,
      signal,
    ),
};
