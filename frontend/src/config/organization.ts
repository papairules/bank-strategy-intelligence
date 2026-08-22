export const AVAILABLE_ORGANIZATIONS = ["Wells Fargo", "BNY", "Goldman Sachs"] as const;

export type Organization = (typeof AVAILABLE_ORGANIZATIONS)[number];

export const DEFAULT_ORGANIZATION: Organization = "Wells Fargo";
