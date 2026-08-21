import { NavLink, Outlet, useLocation } from "react-router-dom";

const navigation = [
  { label: "Overview", path: "/", mark: "OV" },
  { label: "Hiring Intelligence", path: "/hiring", mark: "HI" },
  { label: "Technology Intelligence", path: "/technology", mark: "TI" },
  { label: "Strategic Signals", path: "/signals", mark: "SS" },
  { label: "Evidence", path: "/evidence", mark: "EV" },
];

export function AppShell() {
  const location = useLocation();
  const current = navigation.find((item) => item.path === location.pathname)?.label ?? "Hiring Intelligence";
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark">BSI</span>
          <div><strong>Bank Strategy</strong><span>Intelligence</span></div>
        </div>
        <div className="nav-label">Intelligence workspace</div>
        <nav>
          {navigation.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === "/"} className={({ isActive }) => isActive ? "nav-item nav-item--active" : "nav-item"}>
              <span className="nav-item__mark">{item.mark}</span>{item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar__footer"><span className="status-dot" />Evidence-backed intelligence</div>
      </aside>
      <main className="main-shell">
        <header className="topbar">
          <div><span className="topbar__label">Current workspace</span><strong>{current}</strong></div>
          <div className="topbar__context"><span>Organization</span><strong>Wells Fargo</strong></div>
        </header>
        <Outlet />
      </main>
    </div>
  );
}
