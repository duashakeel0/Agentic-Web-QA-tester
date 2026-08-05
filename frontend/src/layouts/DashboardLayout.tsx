import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import "./DashboardLayout.css";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: "◆" },
  { to: "/run", label: "Run a Test", icon: "▶" },
  { to: "/history", label: "History", icon: "☰" },
  { to: "/compare", label: "Model Comparison", icon: "⇄" },
  { to: "/analytics", label: "Analytics", icon: "▤" },
];

function DashboardLayout({ children }: { children: ReactNode }) {
  const { username, logout } = useAuth();

  return (
    <div className="dashboard-shell app-shell-full-bleed">
      <aside className="dashboard-sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark">◆</span> QA Tester
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}
            >
              <span className="sidebar-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <a className="sidebar-repo-link" href="https://github.com/duashakeel0/Agentic-Web-QA-tester" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </aside>

      <div className="dashboard-body">
        <header className="dashboard-topbar">
          <span className="topbar-greeting">Welcome back, {username ?? "QA tester"}</span>
          <button className="logout-button" onClick={logout} type="button">
            Log out
          </button>
        </header>
        <main className="dashboard-content">{children}</main>
      </div>
    </div>
  );
}

export default DashboardLayout;
