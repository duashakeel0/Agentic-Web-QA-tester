import { useEffect, useState } from "react";
import { apiGet, ApiError } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import "./Overview.css";

interface HistoryStats {
  total_runs: number;
  passed: number;
  failed: number;
  unmatched: number;
  avg_duration_ms: number;
  by_provider: Record<string, number>;
}

function Overview() {
  const { logout } = useAuth();
  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<HistoryStats>("/api/history/stats")
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load stats.");
      });
    return () => {
      cancelled = true;
    };
  }, [logout]);

  const cards = stats
    ? [
        { label: "Total Tests", value: stats.total_runs },
        { label: "Passed", value: stats.passed, tone: "pass" as const },
        { label: "Failed", value: stats.failed, tone: "fail" as const },
        { label: "Avg Runtime", value: `${(stats.avg_duration_ms / 1000).toFixed(1)}s` },
        { label: "Claude Runs", value: stats.by_provider.claude ?? 0 },
        { label: "Ollama Runs", value: stats.by_provider.ollama ?? 0 },
      ]
    : [];

  return (
    <div className="overview-page">
      <h1 className="overview-title">Overview</h1>
      <p className="overview-subtitle">A snapshot of every test your AI QA agents have run so far.</p>

      {error && <p className="overview-error">{error}</p>}

      <div className="stat-grid">
        {stats
          ? cards.map((card) => (
              <div className={`stat-card${card.tone ? ` stat-${card.tone}` : ""}`} key={card.label}>
                <span className="stat-value">{card.value}</span>
                <span className="stat-label">{card.label}</span>
              </div>
            ))
          : Array.from({ length: 6 }).map((_, i) => <div className="stat-card stat-loading" key={i} />)}
      </div>

      {stats && stats.total_runs === 0 && (
        <p className="overview-empty">No tests run yet - head to "Run a Test" to kick off your first one.</p>
      )}
    </div>
  );
}

export default Overview;
