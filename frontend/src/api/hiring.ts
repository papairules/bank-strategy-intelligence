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
    public readonly code?: string,
  ) {
    super(message);
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let message = `Request failed with status ${response.status}`;
  let code: string | undefined;
  try {
    const body = (await response.json()) as {
      detail?: string | { code?: string; message?: string };
    };
    if (typeof body.detail === "string") message = body.detail;
    if (body.detail && typeof body.detail === "object") {
      if (body.detail.message) message = body.detail.message;
      code = body.detail.code;
    }
  } catch {
    // Preserve the safe status-based message.
  }
  return new ApiError(message, response.status, code);
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return response.json() as Promise<T>;
}

export async function postJson<TRequest, TResponse>(
  path: string,
  body: TRequest,
  signal?: AbortSignal,
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await errorFromResponse(response);
  return response.json() as Promise<TResponse>;
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
