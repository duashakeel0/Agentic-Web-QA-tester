import { useState, type FormEvent, type ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  BarChart3,
  ChevronsLeft,
  ChevronsRight,
  Database,
  GitCompare,
  History,
  LayoutDashboard,
  LogOut,
  Moon,
  PlusCircle,
  Search,
  ShieldCheck,
  Sun,
} from "lucide-react";
import GlobalChat from "../components/GlobalChat";
import { useAuth } from "../contexts/AuthContext";
import { useAppTheme } from "../hooks/useAppTheme";
import "./DashboardLayout.css";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/run", label: "New Test", icon: PlusCircle },
  { to: "/history", label: "Test History", icon: History },
  { to: "/compare", label: "Model Comparison", icon: GitCompare },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/domain-knowledge", label: "Domain Knowledge", icon: Database },
];

// Not literal server health - these agents are functions, not long-running
// processes with uptime. "Ready" reflects that every agent is wired up and
// callable, not a fabricated live health check.
const AGENT_READY_STATUS = [
  { name: "Planner", color: "var(--claude-color)" },
  { name: "Explorer", color: "var(--ollama-color)" },
  { name: "Verifier", color: "var(--status-warning)" },
  { name: "Reporter", color: "var(--accent)" },
];

const SIDEBAR_COLLAPSE_KEY = "qa_tester_sidebar_collapsed";

function DashboardLayout({ children }: { children: ReactNode }) {
  const { username, logout } = useAuth();
  const { theme, toggleTheme } = useAppTheme();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === "1");

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }

  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault();
    if (search.trim()) navigate(`/history?search=${encodeURIComponent(search.trim())}`);
  }

  return (
    <div className={`dashboard-shell app-shell-full-bleed${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="dashboard-sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">
            <ShieldCheck size={20} strokeWidth={2.25} />
          </span>
          <div className="sidebar-brand-copy">
            <div className="brand-name">SentinelQA</div>
            <div className="brand-tagline">AI QA Agent</div>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `sidebar-link${isActive ? " active" : ""}`}
              title={collapsed ? item.label : undefined}
            >
              <span className="sidebar-icon" aria-hidden="true">
                <item.icon size={17} strokeWidth={2} />
              </span>
              <span className="sidebar-link-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-agent-status">
          <div className="agent-status-header">
            <span className="sidebar-section-label">Agents</span>
            <span className="agent-status-count">4/4 ready</span>
          </div>
          {AGENT_READY_STATUS.map((agent) => (
            <div className="agent-status-row" key={agent.name}>
              <span className="agent-status-dot" style={{ background: agent.color }} aria-hidden="true" />
              <span className="agent-status-name">{agent.name}</span>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar">{(username ?? "?").slice(0, 1).toUpperCase()}</div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-name">{username ?? "QA tester"}</div>
              <div className="sidebar-user-role">QA Tester</div>
            </div>
          </div>

          <a
            className="sidebar-repo-link"
            href="https://github.com/duashakeel0/Agentic-Web-QA-tester"
            target="_blank"
            rel="noreferrer"
          >
            GitHub
          </a>

          <button
            type="button"
            className="sidebar-collapse-toggle"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
            <span className="sidebar-link-label">Collapse</span>
          </button>
        </div>
      </aside>

      <div className="dashboard-body">
        <header className="dashboard-topbar">
          <form className="topbar-search" onSubmit={handleSearchSubmit} role="search">
            <Search size={15} className="topbar-search-icon" aria-hidden="true" />
            <input
              type="text"
              placeholder="Search test history by ticket or website…"
              aria-label="Search test history"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </form>
          <div className="topbar-actions">
            <button
              type="button"
              className="topbar-icon-button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              title="Toggle theme"
            >
              {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button className="logout-button" onClick={logout} type="button">
              <LogOut size={14} aria-hidden="true" />
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
