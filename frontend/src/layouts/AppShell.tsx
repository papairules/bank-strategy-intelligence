import { NavLink, Outlet, useLocation } from "react-router-dom";
import { CURRENT_ORGANIZATION } from "../config/organization";

const navigation = [
  { label: "Overview", path: "/", mark: "OV", group: "Workspace" },
  { label: "Hiring Intelligence", path: "/hiring", mark: "HI", group: "Intelligence" },
  { label: "Technology Intelligence", path: "/technology", mark: "TI", group: "Intelligence" },
  { label: "Strategic Signals", path: "/signals", mark: "SS", group: "Intelligence" },
  { label: "Evidence Explorer", path: "/evidence", mark: "EV", group: "Evidence" },
  { label: "Ask Evidence", path: "/evidence#ask-evidence", mark: "AE", group: "Governed AI" },
  { label: "Ask Strategy", path: "/signals#ask-strategy", mark: "AS", group: "Governed AI" },
];

export function AppShell() {
  const location = useLocation();
  const current = navigation.find((item) => item.path === `${location.pathname}${location.hash}`)?.label
    ?? navigation.find((item) => !item.path.includes("#") && item.path === location.pathname)?.label
    ?? "Overview";
  const groups = Array.from(new Set(navigation.map((item) => item.group)));
  return (
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
          <div className="topbar__context"><span>Current data scope</span><strong>{CURRENT_ORGANIZATION}</strong></div>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
