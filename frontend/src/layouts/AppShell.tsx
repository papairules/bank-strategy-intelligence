import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { AVAILABLE_ORGANIZATIONS, readStoredOrganization, writeStoredOrganization, type Organization } from "../config/organization";
import { OrganizationProvider } from "../context/OrganizationContext";
import { OrganizationPicker } from "./OrganizationPicker";

const navigation = [
  { label: "Overview", path: "/", mark: "OV", group: "Workspace" },
  { label: "Hiring Intelligence", path: "/hiring", mark: "HI", group: "Intelligence" },
  // { label: "Technology Intelligence", path: "/technology", mark: "TI", group: "Intelligence" },
  { label: "Strategic Signals", path: "/signals", mark: "SS", group: "Intelligence" },
  // { label: "Evidence Explorer", path: "/evidence", mark: "EV", group: "Evidence" },
  // { label: "Ask Evidence", path: "/evidence#ask-evidence", mark: "AE", group: "Governed AI" },
  // { label: "Ask Strategy", path: "/signals#ask-strategy", mark: "AS", group: "Governed AI" },
  { label: "Company Report", path: "/report", mark: "CR", group: "Governed AI" },
];

export function AppShell() {
  const [organization, setOrganizationState] = useState<Organization | null>(() => readStoredOrganization());
  const location = useLocation();
  const current = navigation.find((item) => item.path === `${location.pathname}${location.hash}`)?.label
    ?? navigation.find((item) => !item.path.includes("#") && item.path === location.pathname)?.label
    ?? "Overview";
  const groups = Array.from(new Set(navigation.map((item) => item.group)));

  const setOrganization = (next: Organization) => {
    writeStoredOrganization(next);
    setOrganizationState(next);
  };

  if (organization === null) {
    return <OrganizationPicker onSelect={setOrganization} />;
  }

  return (
    <OrganizationProvider value={{ organization, setOrganization }}>
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark">BSI</span>
          <div><strong>Bank Strategy</strong><span>Intelligence</span></div>
        </div>
        <nav>
          {groups.map((group) => <div className="nav-group" key={group}><div className="nav-label">{group}</div>{navigation.filter((item) => item.group === group).map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === "/"} className={({ isActive }) => {
              const hash = item.path.includes("#") ? item.path.slice(item.path.indexOf("#")) : "";
              const active = hash ? isActive && location.hash === hash : isActive && !location.hash;
              return active ? "nav-item nav-item--active" : "nav-item";
            }}>
              <span className="nav-item__mark">{item.mark}</span>{item.label}
            </NavLink>
          ))}</div>)}
        </nav>
        <div className="sidebar__footer"><span className="status-dot" />Evidence-backed intelligence</div>
      </aside>
      <main className="main-shell">
        <header className="topbar">
          <div><span className="topbar__label">Current workspace</span><strong>{current}</strong></div>
          <label className="topbar__context"><span>Current data scope</span><select aria-label="Organization" value={organization} onChange={(event) => setOrganization(event.target.value as Organization)}>{AVAILABLE_ORGANIZATIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
        </header>
        <div key={organization}><Outlet /></div>
      </main>
    </div>
    </OrganizationProvider>
  );
}
