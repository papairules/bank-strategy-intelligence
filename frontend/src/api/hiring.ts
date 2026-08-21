import type {
  HiringAnalytics,
  JobDetail,
  JobFilters,
  JobListResponse,
  OrganizationSummary,
  SignalsResponse,
} from "../types/hiring";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
export const API_BASE_URL = (configuredBaseUrl || "http://localhost:8000").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Preserve the safe status-based message.
    }
    throw new ApiError(message, response.status);
  }
  return response.json() as Promise<T>;
}

function organizationPath(organization: string): string {
  return `/api/v1/hiring/organizations/${encodeURIComponent(organization)}`;
}

export function buildJobsPath(
  organization: string,
  filters: JobFilters,
): string {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.location) params.set("location", filters.location);
  if (filters.capability) params.set("capability", filters.capability);
  if (filters.seniority) params.set("seniority", filters.seniority);
  return `${organizationPath(organization)}/jobs?${params.toString()}`;
}

export const hiringApi = {
  summary: (organization: string, signal?: AbortSignal) =>
    getJson<OrganizationSummary>(`${organizationPath(organization)}/summary`, signal),
  analytics: (organization: string, signal?: AbortSignal) =>
    getJson<HiringAnalytics>(`${organizationPath(organization)}/analytics`, signal),
  signals: (organization: string, signal?: AbortSignal) =>
    getJson<SignalsResponse>(`${organizationPath(organization)}/signals`, signal),
  jobs: (organization: string, filters: JobFilters, signal?: AbortSignal) =>
    getJson<JobListResponse>(buildJobsPath(organization, filters), signal),
  jobDetail: (jobId: string, signal?: AbortSignal) =>
    getJson<JobDetail>(`/api/v1/hiring/jobs/${encodeURIComponent(jobId)}`, signal),
};
