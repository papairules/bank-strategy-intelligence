import { getJson } from "./hiring";
import type {
  EvidenceRecordFilters,
  EvidenceRecordsResponse,
  EvidenceSummary,
  UnifiedEvidenceDetail,
} from "../types/evidence";

function organizationPath(organization: string): string {
  return `/api/v1/evidence/organizations/${encodeURIComponent(organization)}`;
}

export function buildEvidenceRecordsPath(
  organization: string,
  filters: EvidenceRecordFilters,
): string {
  const params = new URLSearchParams({ limit: String(filters.limit), offset: String(filters.offset) });
  if (filters.search) params.set("search", filters.search);
  if (filters.source) params.set("source", filters.source);
  if (filters.enriched !== undefined) params.set("enriched", String(filters.enriched));
  if (filters.technology) params.set("technology", filters.technology);
  if (filters.capability) params.set("capability", filters.capability);
  if (filters.location) params.set("location", filters.location);
  return `${organizationPath(organization)}/records?${params.toString()}`;
}

export function buildEvidenceDetailPath(
  organization: string,
  evidenceId: string,
): string {
  const params = new URLSearchParams({ organization });
  return `/api/v1/evidence/${encodeURIComponent(evidenceId)}?${params.toString()}`;
}

export const evidenceApi = {
  summary: (organization: string, signal?: AbortSignal) =>
    getJson<EvidenceSummary>(`${organizationPath(organization)}/summary`, signal),
  records: (organization: string, filters: EvidenceRecordFilters, signal?: AbortSignal) =>
    getJson<EvidenceRecordsResponse>(buildEvidenceRecordsPath(organization, filters), signal),
  detail: (organization: string, evidenceId: string, signal?: AbortSignal) =>
    getJson<UnifiedEvidenceDetail>(buildEvidenceDetailPath(organization, evidenceId), signal),
};
