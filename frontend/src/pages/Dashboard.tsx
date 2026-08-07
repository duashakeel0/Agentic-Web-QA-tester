import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Bug,
  CheckCircle2,
  Clock3,
  Coins,
  ListChecks,
  Rocket,
  RotateCcw,
  Target,
} from "lucide-react";
import AskAboutTest from "../components/AskAboutTest";
import BarList from "../components/charts/BarList";
import DonutChart from "../components/charts/DonutChart";
import LineChart from "../components/charts/LineChart";
import ProgressRing from "../components/charts/ProgressRing";
import ComparisonSummary from "../components/ComparisonSummary";
import LiveBrowserView from "../components/LiveBrowserView";
import ModelSelector from "../components/ModelSelector";
import PipelineTimeline from "../components/PipelineTimeline";
import ReportCard from "../components/ReportCard";
import TalkingAgentsPanel from "../components/TalkingAgentsPanel";
import { useAuth } from "../contexts/AuthContext";
import { usePipelineRun, type RunStatus } from "../hooks/usePipelineRun";
import { apiGet, ApiError } from "../services/api";
import type { DailyStat, HistoryEntry, HistoryStats, ProviderStats } from "../types/history";
import type { ModelChoice, Provider } from "../types/pipeline";
import "./Dashboard.css";

// Claude first, then Ollama - the order the combined report reads in:
// each provider's full report, then the comparison beneath both.
const PROVIDER_ORDER: Provider[] = ["claude", "ollama"];

const AGENT_READY_ROW = [
  { name: "Planner", color: "var(--claude-color)" },
  { name: "Explorer", color: "var(--accent-blue)" },
  { name: "Verifier", color: "var(--status-warning)" },
  { name: "Reporter", color: "var(--accent)" },
];

const PROVIDER_LABELS: Record<string, string> = { claude: "Claude", ollama: "Llama (Ollama)" };

function formatDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

interface Toast {
  id: number;
  tone: "success" | "error" | "info";
  text: string;
}

/** Small self-dismissing toast stack, driven entirely by transitions on the
 * run's existing status/errorMessage/comparison state - no new backend
 * events, just surfacing what usePipelineRun already tells us. */
function useRunToasts(status: RunStatus, errorMessage: string | null, ticketId: string) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(0);
  const prevStatus = useRef<RunStatus>(status);

  useEffect(() => {
    if (prevStatus.current === status) return;
    const prev = prevStatus.current;
    prevStatus.current = status;

    if (status === "done" && prev !== "idle") {
      idRef.current += 1;
      setToasts((t) => [...t, { id: idRef.current, tone: "success", text: `Run finished for ticket ${ticketId}.` }]);
    } else if (status === "error") {
      idRef.current += 1;
      setToasts((t) => [...t, { id: idRef.current, tone: "error", text: errorMessage ?? "Run failed." }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  useEffect(() => {
    if (toasts.length === 0) return;
    const timers = toasts.map((toast) =>
      setTimeout(() => setToasts((t) => t.filter((x) => x.id !== toast.id)), 5000),
    );
    return () => timers.forEach(clearTimeout);
  }, [toasts]);

  function dismiss(id: number) {
    setToasts((t) => t.filter((x) => x.id !== id));
  }

  return { toasts, dismiss };
}

function Dashboard() {
  const { username, logout } = useAuth();
  const [ticketId, setTicketId] = useState("");
  const [model, setModel] = useState<ModelChoice>("claude");
  const { status, feed, stages, frames, frameHistory, results, historyIds, comparison, errorMessage, start, reset } =
    usePipelineRun();
  const { toasts, dismiss } = useRunToasts(status, errorMessage, ticketId);

  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [providerStats, setProviderStats] = useState<ProviderStats[]>([]);
  const [recentRuns, setRecentRuns] = useState<HistoryEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const running = status === "connecting" || status === "running";
  const resultList = PROVIDER_ORDER.map((p) => results[p]).filter((r) => r !== undefined);
  const primaryHistoryId = historyIds.claude ?? historyIds.ollama;
  const activeProviders = Object.keys(stages);

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

  // Weighted (by run count) average across whichever providers have data -
  // real numbers already returned by /api/history/provider-stats, just
  // rolled up for the top-level stat row instead of shown per-provider only.
  const weightedAverage = (pick: (p: ProviderStats) => number): number | null => {
    const totalRuns = providerStats.reduce((sum, p) => sum + p.run_count, 0);
    if (totalRuns === 0) return null;
    return providerStats.reduce((sum, p) => sum + pick(p) * p.run_count, 0) / totalRuns;
  };
  const avgCoverage = weightedAverage((p) => p.avg_coverage_ratio);
  const avgAccuracy = weightedAverage((p) => p.avg_accuracy_ratio);

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
        { label: "Total Tests", value: `${stats.total_runs}`, icon: ListChecks, tone: "neutral" as const },
        {
          label: "Pass Rate",
          value: stats.total_runs > 0 ? `${Math.round((stats.passed / stats.total_runs) * 100)}%` : "–",
          icon: CheckCircle2,
          tone: "pass" as const,
        },
        {
          label: "Avg Coverage",
          value: avgCoverage !== null ? `${Math.round(avgCoverage * 100)}%` : "–",
          icon: Target,
          tone: "neutral" as const,
        },
        {
          label: "Avg Accuracy",
          value: avgAccuracy !== null ? `${Math.round(avgAccuracy * 100)}%` : "–",
          icon: CheckCircle2,
          tone: "neutral" as const,
        },
        {
          label: "Avg Duration",
          value: `${(stats.avg_duration_ms / 1000).toFixed(1)}s`,
          icon: Clock3,
          tone: "neutral" as const,
        },
        { label: "Total Cost", value: `$${stats.total_cost_usd.toFixed(4)}`, icon: Coins, tone: "neutral" as const },
      ]
    : [];

  return (
    <div className="dash-page">
      {toasts.length > 0 && (
        <div className="dash-toast-stack" role="status" aria-live="polite">
          {toasts.map((toast) => (
            <div className={`dash-toast dash-toast-${toast.tone}`} key={toast.id}>
              {toast.tone === "error" ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />}
              <span>{toast.text}</span>
              <button type="button" aria-label="Dismiss notification" onClick={() => dismiss(toast.id)}>
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <header className="dash-hero">
        <div className="dash-hero-copy">
          <span className="dash-hero-eyebrow">AI Command Center</span>
          <h1>Welcome back, {username ?? "Dua"}! 👋</h1>
          <p>
            Your AI testing team is online and ready to analyze your next website. Enter a URL or connect a Trello
            ticket to get started.
          </p>
        </div>
        <div className="dash-hero-agent-row" aria-label="Agent readiness">
          {AGENT_READY_ROW.map((agent) => (
            <span className="dash-hero-agent-chip" key={agent.name}>
              <span className="dash-hero-agent-dot" style={{ background: agent.color }} aria-hidden="true" />
              {agent.name}
            </span>
          ))}
        </div>
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
            aria-label="Trello ticket ID"
            disabled={running}
            className="dash-ticket-input"
          />
          <ModelSelector value={model} onChange={setModel} disabled={running} />
          <button type="submit" className="dash-launch-btn" disabled={running || !ticketId.trim()}>
            <Rocket size={16} aria-hidden="true" />
            {running ? "Running…" : "Launch Test"}
          </button>
        </form>
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
                <RotateCcw size={12} aria-hidden="true" />
                Reset
              </button>
            )}
          </div>
        )}
        {errorMessage && (
          <div className="dash-error">
            <AlertTriangle size={14} aria-hidden="true" />
            {errorMessage}
          </div>
        )}
      </section>

      {loadError && (
        <p className="dash-error">
          <AlertTriangle size={14} aria-hidden="true" />
          {loadError}
        </p>
      )}

      <section className="dash-stat-grid">
        {stats
          ? statCards.map((card) => (
              <div className={`dash-stat-card${card.tone !== "neutral" ? ` stat-${card.tone}` : ""}`} key={card.label}>
                <span className="dash-stat-icon" aria-hidden="true">
                  <card.icon size={16} />
                </span>
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
              <div className="dash-panel-heading">
                <h2 className="dash-panel-title">Live Run</h2>
                <div className="dash-live-providers">
                  {activeProviders.map((p) => (
                    <span className={`dash-live-provider-tag dash-live-provider-${p}`} key={p}>
                      {PROVIDER_LABELS[p] ?? p}
                    </span>
                  ))}
                </div>
              </div>
              <div className="dash-live-row">
                <div className="dash-live-timeline">
                  <PipelineTimeline stages={stages} />
                  {status === "running" && <ProgressRing percent={progressPercent} label="In Progress" />}
                </div>
                <TalkingAgentsPanel feed={feed} showProvider={Object.keys(stages).length > 1} />
              </div>

              <div className="dash-live-browsers">
                {activeProviders.map((p) => (
                  <LiveBrowserView
                    provider={p as Provider}
                    frame={frames[p as Provider]}
                    history={frameHistory[p as Provider] ?? []}
                    key={p}
                  />
                ))}
              </div>
            </section>
          )}

          {resultList.length > 0 && (
            <section className="dash-panel">
              <h2 className="dash-panel-title">{resultList.length > 1 ? "Full Comparison Report" : "Report"}</h2>
              <div className="dash-report-stack">
                {resultList.map((result) => (
                  <ReportCard result={result} historyId={historyIds[result.provider]} key={result.provider} />
                ))}
                {comparison && (
                  <ComparisonSummary comparison={comparison} claudeResult={results.claude} ollamaResult={results.ollama} />
                )}
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
              <h3>
                <Bug size={13} aria-hidden="true" /> Commonly Missed Steps
              </h3>
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
              {recentRuns.length === 0 && <p className="dash-empty">No tests run yet. Launch one above to get started.</p>}
              {recentRuns.map((run) => (
                <Link to={`/history/${run.id}`} className="dash-history-row" key={run.id}>
                  <div>
                    <div className="dash-history-website">{run.matched ? `${run.domain}/${run.workflow}` : "unmatched"}</div>
                    <div className="dash-history-ticket">
                      {run.ticket_id} · {PROVIDER_LABELS[run.provider] ?? run.provider}
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
    </div>
  );
}

export default Dashboard;
