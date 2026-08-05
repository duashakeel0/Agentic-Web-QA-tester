import { useState, type FormEvent, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import GlobalChat from "../components/GlobalChat";
import { useAuth } from "../contexts/AuthContext";
import { useAppTheme } from "../hooks/useAppTheme";
import "./DashboardLayout.css";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: "⌂" },
  { to: "/run", label: "New Test", icon: "+" },
  { to: "/history", label: "Test History", icon: "☰" },
  { to: "/compare", label: "Model Comparison", icon: "⇄" },
  { to: "/analytics", label: "Analytics", icon: "▤" },
];

// Not literal server health - these agents are functions, not long-running
// processes with uptime. "Ready" reflects that every agent is wired up and
// callable, not a fabricated live health check.
const AGENT_READY_STATUS = [
  { name: "Planner Agent", color: "var(--claude-color)" },
  { name: "Explorer Agent", color: "var(--ollama-color)" },
  { name: "Verifier Agent", color: "var(--status-warning)" },
  { name: "Reporter Agent", color: "var(--accent)" },
];

function DashboardLayout({ children }: { children: ReactNode }) {
  const { username, logout } = useAuth();
  const { theme, toggleTheme } = useAppTheme();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault();
    if (search.trim()) navigate(`/history?search=${encodeURIComponent(search.trim())}`);
  }

  return (
    <div className="dashboard-shell app-shell-full-bleed">
      <aside className="dashboard-sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark">🛡️</span>
          <div>
            <div className="brand-name">SentinelQA</div>
            <div className="brand-tagline">AI QA Agent</div>
          </div>
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

        <div className="sidebar-agent-status">
          <div className="agent-status-header">
            <span>AI Agents</span>
            <span className="agent-status-count">4/4 Ready</span>
          </div>
          {AGENT_READY_STATUS.map((agent) => (
            <div className="agent-status-row" key={agent.name}>
              <span className="agent-status-dot" style={{ background: agent.color }} />
              {agent.name}
            </div>
          ))}
        </div>

        <div className="sidebar-user">
          <div className="sidebar-avatar">{(username ?? "?").slice(0, 1).toUpperCase()}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-user-name">{username ?? "QA tester"}</div>
            <div className="sidebar-user-role">QA Tester</div>
          </div>
        </div>

        <a className="sidebar-repo-link" href="https://github.com/duashakeel0/Agentic-Web-QA-tester" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </aside>

      <div className="dashboard-body">
        <header className="dashboard-topbar">
          <form className="topbar-search" onSubmit={handleSearchSubmit}>
            <span className="topbar-search-icon">⌕</span>
            <input
              type="text"
              placeholder="Search test history…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </form>
          <div className="topbar-actions">
            <button type="button" className="topbar-icon-button" onClick={toggleTheme} title="Toggle theme">
              {theme === "dark" ? "☀" : "☾"}
            </button>
            <button className="logout-button" onClick={logout} type="button">
              Log out
            </button>
          </div>
        </header>
        <main className="dashboard-content">{children}</main>
      </div>

      <GlobalChat />
    </div>
  );
}

export default DashboardLayout;
