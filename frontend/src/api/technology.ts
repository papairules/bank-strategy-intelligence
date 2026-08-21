import { getJson } from "./hiring";
import type {
  TechnologyAnalytics,
  TechnologyObservationList,
  TechnologySummary,
  TechnologySignalsResponse,
} from "../types/technology";

function organizationPath(organization: string): string {
  return `/api/v1/technology/organizations/${encodeURIComponent(organization)}`;
}

export interface TechnologyObservationFilters {
  technology?: string;
  category?: string;
  businessUnit?: string;
  location?: string;
  limit: number;
  offset: number;
}

export function buildTechnologyObservationsPath(
  organization: string,
  filters: TechnologyObservationFilters,
): string {
  const params = new URLSearchParams({
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.technology) params.set("technology", filters.technology);
  if (filters.category) params.set("category", filters.category);
  if (filters.businessUnit) params.set("business_unit", filters.businessUnit);
  if (filters.location) params.set("location", filters.location);
  return `${organizationPath(organization)}/observations?${params.toString()}`;
}

export const technologyApi = {
  summary: (organization: string, signal?: AbortSignal) =>
    getJson<TechnologySummary>(`${organizationPath(organization)}/summary`, signal),
  analytics: (organization: string, signal?: AbortSignal) =>
    getJson<TechnologyAnalytics>(`${organizationPath(organization)}/analytics`, signal),
  signals: (organization: string, signal?: AbortSignal) =>
    getJson<TechnologySignalsResponse>(`${organizationPath(organization)}/signals`, signal),
  observations: (
    organization: string,
    filters: TechnologyObservationFilters,
    signal?: AbortSignal,
  ) => getJson<TechnologyObservationList>(
    buildTechnologyObservationsPath(organization, filters),
    signal,
  ),
};
