import { getJson } from "./hiring";
import type { StrategicSignalsResponse } from "../types/strategy";

export function buildStrategicSignalsPath(organization: string): string {
  return `/api/v1/strategy/organizations/${encodeURIComponent(organization)}/signals`;
}

export const strategyApi = {
  signals: (organization: string, signal?: AbortSignal) =>
    getJson<StrategicSignalsResponse>(buildStrategicSignalsPath(organization), signal),
};
