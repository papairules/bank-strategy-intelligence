import { FormEvent, useState } from "react";
import { AVAILABLE_ORGANIZATIONS, type Organization } from "../config/organization";

export function OrganizationPicker({ onSelect }: { onSelect: (organization: Organization) => void }) {
  const [organization, setOrganization] = useState<Organization | "">("");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (organization) onSelect(organization);
  };

  return (
    <div className="org-picker">
      <div className="org-picker__card">
        <span className="eyebrow">Bank Strategy Intelligence</span>
        <h1>Select a company</h1>
        <p>Select a company to explore its intelligence workspace.</p>
        <form className="org-picker__form" onSubmit={submit}>
          <label htmlFor="entry-organization">Company</label>
          <select id="entry-organization" value={organization} onChange={(event) => setOrganization(event.target.value as Organization)}>
            <option value="" disabled>Select a company</option>
            {AVAILABLE_ORGANIZATIONS.map((item) => <option key={item}>{item}</option>)}
          </select>
          <button className="primary-button" disabled={!organization}>Enter Workspace</button>
        </form>
      </div>
    </div>
  );
}
