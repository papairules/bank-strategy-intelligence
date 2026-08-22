import { createContext, useContext } from "react";
import { DEFAULT_ORGANIZATION, type Organization } from "../config/organization";

interface OrganizationContextValue {
  organization: Organization;
  setOrganization: (organization: Organization) => void;
}

const OrganizationContext = createContext<OrganizationContextValue>({
  organization: DEFAULT_ORGANIZATION,
  setOrganization: () => undefined,
});

export const OrganizationProvider = OrganizationContext.Provider;

export function useOrganization() {
  return useContext(OrganizationContext);
}
