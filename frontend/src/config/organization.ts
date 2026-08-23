export const AVAILABLE_ORGANIZATIONS = ["Wells Fargo", "BNY", "Goldman Sachs", "Citibank", "Morgan Stanley", "Barclays"] as const;

export type Organization = (typeof AVAILABLE_ORGANIZATIONS)[number];

const ORGANIZATION_STORAGE_KEY = "bsi:selected-organization";

function isOrganization(value: unknown): value is Organization {
  return typeof value === "string" && (AVAILABLE_ORGANIZATIONS as readonly string[]).includes(value);
}

export function readStoredOrganization(): Organization | null {
  try {
    const stored = window.localStorage.getItem(ORGANIZATION_STORAGE_KEY);
    return isOrganization(stored) ? stored : null;
  } catch {
    return null;
  }
}

export function writeStoredOrganization(organization: Organization): void {
  try {
    window.localStorage.setItem(ORGANIZATION_STORAGE_KEY, organization);
  } catch {
    // Storage may be unavailable (private browsing, disabled storage); selection still works in-memory.
  }
}
