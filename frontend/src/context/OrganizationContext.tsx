import { createContext, useContext } from "react";
import type { Organization } from "../config/organization";

interface OrganizationContextValue {
  organization: Organization | null;
  setOrganization: (organization: Organization) => void;
}

const OrganizationContext = createContext<OrganizationContextValue>({
  organization: null,
  setOrganization: () => undefined,
});

export const OrganizationProvider = OrganizationContext.Provider;

export function useOrganization(): { organization: Organization; setOrganization: (organization: Organization) => void } {
  const value = useContext(OrganizationContext);
  if (value.organization === null) {
    throw new Error("useOrganization must be used after an organization has been selected.");
  }
  return { organization: value.organization, setOrganization: value.setOrganization };
}
