import { AVAILABLE_ORGANIZATIONS, type Organization } from "../config/organization";

export function OrganizationPicker({ onSelect }: { onSelect: (organization: Organization) => void }) {
  return (
    <div className="org-picker">
      <div className="org-picker__card">
        <span className="eyebrow">Bank Strategy Intelligence</span>
        <h1>Select a bank to continue</h1>
        <p>Choose the organization you want to research. Every view is scoped to a single bank at a time.</p>
        <div className="org-picker__options">
          {AVAILABLE_ORGANIZATIONS.map((item) => (
            <button key={item} type="button" className="org-picker__option" onClick={() => onSelect(item)}>
              {item}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
