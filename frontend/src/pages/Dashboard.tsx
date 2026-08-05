import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import AskAboutTest from "../components/AskAboutTest";
import BarList from "../components/charts/BarList";
import DonutChart from "../components/charts/DonutChart";
import LineChart from "../components/charts/LineChart";
import ProgressRing from "../components/charts/ProgressRing";
import ModelSelector from "../components/ModelSelector";
import PipelineTimeline from "../components/PipelineTimeline";
import ReportCard from "../components/ReportCard";
import TalkingAgentsPanel from "../components/TalkingAgentsPanel";
import { useAuth } from "../contexts/AuthContext";
import { usePipelineRun } from "../hooks/usePipelineRun";
import { apiGet, ApiError } from "../services/api";
import type { DailyStat, HistoryEntry, HistoryStats, ProviderStats } from "../types/history";
import type { ModelChoice } from "../types/pipeline";
import "./Dashboard.css";

function formatDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

function Dashboard() {
  const { username, logout } = useAuth();
  const [ticketId, setTicketId] = useState("");
  const [model, setModel] = useState<ModelChoice>("claude");
  const { status, feed, stages, results, historyIds, comparison, errorMessage, start, reset } = usePipelineRun();

  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [providerStats, setProviderStats] = useState<ProviderStats[]>([]);
  const [recentRuns, setRecentRuns] = useState<HistoryEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const running = status === "connecting" || status === "running";
  const resultList = Object.values(results);
  const primaryHistoryId = historyIds.claude ?? historyIds.ollama;

  function reloadDashboardData() {
    Promise.all([
      apiGet<HistoryStats>("/api/history/stats"),
      apiGet<DailyStat[]>("/api/history/daily?days=7"),
      apiGet<ProviderStats[]>("/api/history/provider-stats"),
      apiGet<HistoryEntry[]>("/api/history?limit=6"),
    ])
      .then(([s, d, p, r]) => {
        setStats(s);
        setDaily(d);
        setProviderStats(p);
        setRecentRuns(r);
        setLoadError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setLoadError(err instanceof Error ? err.message : "Could not load dashboard data.");
      });
  }

  useEffect(reloadDashboardData, [logout]);
  // Refresh the panels once a run finishes so the numbers aren't stale.
  useEffect(() => {
    if (status === "done") reloadDashboardData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const progressPercent = useMemo(() => {
    const providers = Object.keys(stages);
    if (providers.length === 0) return 0;
    const doneCount = providers.reduce((sum, p) => {
      const stageMap = stages[p as keyof typeof stages];
      if (!stageMap) return sum;
      return sum + Object.values(stageMap).filter((s) => s.status === "done").length;
    }, 0);
    return (doneCount / (providers.length * 4)) * 100;
  }, [stages]);

  const claudeProvider = providerStats.find((p) => p.provider === "claude");
  const ollamaProvider = providerStats.find((p) => p.provider === "ollama");
  const commonMissedSteps = useMemo(() => {
    const merged = new Map<string, number>();
    for (const p of providerStats) {
      for (const m of p.common_missed_steps) {
        merged.set(m.step, (merged.get(m.step) ?? 0) + m.count);
      }
    }
    return Array.from(merged.entries())
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);
  }, [providerStats]);

  const statCards = stats
    ? [
        { label: "Total Tests", value: stats.total_runs },
        { label: "Passed", value: stats.passed, tone: "pass" as const },
        { label: "Failed", value: stats.failed, tone: "fail" as const },
        { label: "Avg Duration", value: `${(stats.avg_duration_ms / 1000).toFixed(1)}s` },
        { label: "Total Cost", value: `$${stats.total_cost_usd.toFixed(4)}` },
        { label: "Issues Found", value: recentRuns.reduce((sum, r) => sum + r.findings_count, 0) },
      ]
    : [];

  return (
    <div className="dash-page">
      <header className="dash-hero">
        <h1>Welcome back, {username ?? "Dua"}! 👋</h1>
        <p>
          Your AI testing team is online and ready to analyze your next website. Enter a URL or connect a Trello
          ticket to get started.
        </p>
      </header>

      <section className="dash-panel dash-start-panel">
        <div className="dash-panel-heading">
          <h2>Start a new test</h2>
          <span className="dash-panel-subtext">Enter a Trello ticket ID for a registered website.</span>
        </div>
        <form
          className="dash-start-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (ticketId.trim()) start(ticketId.trim(), model);
          }}
        >
          <input
            type="text"
            value={ticketId}
            onChange={(event) => setTicketId(event.target.value)}
            placeholder="Trello ticket ID…"
            disabled={running}
          />
          <button type="submit" disabled={running || !ticketId.trim()}>
            {running ? "Running…" : "Start Test →"}
          </button>
        </form>
        <ModelSelector value={model} onChange={setModel} disabled={running} />
        {status !== "idle" && (
          <div className="dash-status-row">
            <span className={`status-dot status-${status}`} />
            <span>
              {status === "connecting" && "Connecting…"}
              {status === "running" && "Agents are working…"}
              {status === "done" && "Run complete."}
              {status === "error" && "Run failed."}
            </span>
            {status !== "running" && status !== "connecting" && (
              <button type="button" className="dash-reset-link" onClick={reset}>
                Reset
              </button>
            )}
          </div>
        )}
        {errorMessage && <div className="dash-error">{errorMessage}</div>}
      </section>

      {loadError && <p className="dash-error">{loadError}</p>}

      <section className="dash-stat-grid">
        {stats
          ? statCards.map((card) => (
              <div className={`dash-stat-card${card.tone ? ` stat-${card.tone}` : ""}`} key={card.label}>
                <span className="dash-stat-value">{card.value}</span>
                <span className="dash-stat-label">{card.label}</span>
              </div>
            ))
          : Array.from({ length: 6 }).map((_, i) => <div className="dash-stat-card dash-stat-loading" key={i} />)}
      </section>

      <div className="dash-grid">
        <div className="dash-main-col">
          {status !== "idle" && (
            <section className="dash-panel">
              <h2 className="dash-panel-title">Live Run</h2>
              <div className="dash-live-row">
                <div className="dash-live-timeline">
                  <PipelineTimeline stages={stages} />
                  {status === "running" && <ProgressRing percent={progressPercent} label="In Progress" />}
                </div>
                <TalkingAgentsPanel feed={feed} showProvider={Object.keys(stages).length > 1} />
              </div>
            </section>
          )}

          {resultList.length > 0 && (
            <section className="dash-panel">
              <h2 className="dash-panel-title">Report{resultList.length > 1 ? "s" : ""}</h2>
              <div className="dash-report-grid">
                {resultList.map((result) => (
                  <ReportCard result={result} historyId={historyIds[result.provider]} key={result.provider} />
                ))}
              </div>
              {primaryHistoryId && <AskAboutTest runId={primaryHistoryId} />}
            </section>
          )}

          <section className="dash-panel dash-charts-row">
            <div className="dash-chart-block">
              <h3>
                Tests Over Time <span className="dash-chart-note">Last 7 days</span>
              </h3>
              <LineChart data={daily.map((d) => ({ label: d.date.slice(5), value: d.total }))} color="var(--accent)" />
            </div>
            <div className="dash-chart-block">
              <h3>
                Success Rate <span className="dash-chart-note">Last 7 days</span>
              </h3>
              <DonutChart
                centerLabel="Passed"
                segments={[
                  { label: "Passed", value: daily.reduce((s, d) => s + d.passed, 0), color: "var(--status-good)" },
                  { label: "Failed", value: daily.reduce((s, d) => s + d.failed, 0), color: "var(--status-critical)" },
                ]}
              />
            </div>
          </section>

          <section className="dash-panel dash-charts-row">
            <div className="dash-chart-block">
              <h3>
                Cost Trend <span className="dash-chart-note">Last 7 days</span>
              </h3>
              <LineChart
                data={daily.map((d) => ({ label: d.date.slice(5), value: d.total_cost_usd }))}
                color="var(--claude-color)"
                formatValue={(v) => `$${v.toFixed(3)}`}
              />
            </div>
            <div className="dash-chart-block">
              <h3>Commonly Missed Steps</h3>
              <BarList items={commonMissedSteps} defaultColor="var(--status-warning)" />
            </div>
          </section>
        </div>

        <aside className="dash-side-col">
          <section className="dash-panel">
            <div className="dash-panel-heading">
              <h2>Test History</h2>
              <Link to="/history" className="dash-panel-link">
                View All
              </Link>
            </div>
            <div className="dash-history-list">
              {recentRuns.length === 0 && <p className="dash-empty">No tests run yet.</p>}
              {recentRuns.map((run) => (
                <Link to={`/history/${run.id}`} className="dash-history-row" key={run.id}>
                  <div>
                    <div className="dash-history-website">{run.matched ? `${run.domain}/${run.workflow}` : "unmatched"}</div>
                    <div className="dash-history-ticket">
                      {run.ticket_id} · {run.provider}
                    </div>
                  </div>
                  <div className="dash-history-right">
                    <span className={`dash-history-status status-${run.verdict ?? "unmatched"}`}>
                      {run.verdict?.toUpperCase() ?? "N/A"}
                    </span>
                    <span className="dash-history-time">{formatDate(run.created_at)}</span>
                  </div>
                </Link>
              ))}
            </div>
          </section>

          <section className="dash-panel">
            <div className="dash-panel-heading">
              <h2>Model Comparison</h2>
              <Link to="/compare" className="dash-panel-link">
                Details
              </Link>
            </div>
            {claudeProvider && ollamaProvider ? (
              <table className="dash-compare-table">
                <thead>
                  <tr>
                    <th />
                    <th>Claude</th>
                    <th>Ollama</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Runs</td>
                    <td>{claudeProvider.run_count}</td>
                    <td>{ollamaProvider.run_count}</td>
                  </tr>
                  <tr>
                    <td>Avg Latency</td>
                    <td>{(claudeProvider.avg_duration_ms / 1000).toFixed(1)}s</td>
                    <td>{(ollamaProvider.avg_duration_ms / 1000).toFixed(1)}s</td>
                  </tr>
                  <tr>
                    <td>Accuracy</td>
                    <td>{Math.round(claudeProvider.avg_accuracy_ratio * 100)}%</td>
                    <td>{Math.round(ollamaProvider.avg_accuracy_ratio * 100)}%</td>
                  </tr>
                  <tr>
                    <td>Cost / Test</td>
                    <td>${claudeProvider.avg_cost_usd.toFixed(4)}</td>
                    <td>${ollamaProvider.avg_cost_usd.toFixed(4)}</td>
                  </tr>
                </tbody>
              </table>
            ) : (
              <p className="dash-empty">Run a "Compare Both" test to see model comparison data.</p>
            )}
          </section>
        </aside>
      </div>

      {comparison && (
        <section className="dash-panel">
          <h2 className="dash-panel-title">Comparison Summary</h2>
          <p className="dash-comparison-text">{comparison.summary}</p>
        </section>
      )}
    </div>
  );
}

export default Dashboard;
