import { useEffect, useState } from "react";
import BarList from "../components/charts/BarList";
import DonutChart from "../components/charts/DonutChart";
import LineChart from "../components/charts/LineChart";
import { apiGet, ApiError } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import type { DailyStat, ProviderStats } from "../types/history";
import "./Analytics.css";

const RANGES = [7, 14, 30];

function Analytics() {
  const { logout } = useAuth();
  const [days, setDays] = useState(7);
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [providerStats, setProviderStats] = useState<ProviderStats[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiGet<DailyStat[]>(`/api/history/daily?days=${days}`),
      apiGet<ProviderStats[]>("/api/history/provider-stats"),
    ])
      .then(([d, p]) => {
        setDaily(d);
        setProviderStats(p);
        setError(null);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load analytics.");
      });
  }, [days, logout]);

  const totalPassed = daily.reduce((s, d) => s + d.passed, 0);
  const totalFailed = daily.reduce((s, d) => s + d.failed, 0);
  const commonMissedSteps = (() => {
    const merged = new Map<string, number>();
    for (const p of providerStats) {
      for (const m of p.common_missed_steps) merged.set(m.step, (merged.get(m.step) ?? 0) + m.count);
    }
    return Array.from(merged.entries())
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 6);
  })();

  return (
    <div className="analytics-page">
      <div className="analytics-header">
        <div>
          <h1 className="analytics-title">Analytics</h1>
          <p className="analytics-subtitle">Trends across every test run.</p>
        </div>
        <div className="analytics-range">
          {RANGES.map((r) => (
            <button key={r} type="button" className={r === days ? "active" : ""} onClick={() => setDays(r)}>
              {r}d
            </button>
          ))}
        </div>
      </div>

      {error && <p className="analytics-error">{error}</p>}

      <div className="analytics-grid">
        <div className="analytics-panel">
          <h3>
            Tests Over Time <span className="analytics-note">Last {days} days</span>
          </h3>
          <LineChart data={daily.map((d) => ({ label: d.date.slice(5), value: d.total }))} color="var(--accent)" />
        </div>
        <div className="analytics-panel">
          <h3>
            Success Rate <span className="analytics-note">Last {days} days</span>
          </h3>
          <DonutChart
            centerLabel="Passed"
            segments={[
              { label: "Passed", value: totalPassed, color: "var(--status-good)" },
              { label: "Failed", value: totalFailed, color: "var(--status-critical)" },
            ]}
          />
        </div>
        <div className="analytics-panel">
          <h3>
            Average Runtime <span className="analytics-note">Last {days} days</span>
          </h3>
          <LineChart
            data={daily.map((d) => ({ label: d.date.slice(5), value: d.avg_duration_ms / 1000 }))}
            color="var(--claude-color)"
            formatValue={(v) => `${v.toFixed(1)}s`}
          />
        </div>
        <div className="analytics-panel">
          <h3>
            Cost Trend <span className="analytics-note">Last {days} days</span>
          </h3>
          <LineChart
            data={daily.map((d) => ({ label: d.date.slice(5), value: d.total_cost_usd }))}
            color="var(--ollama-color)"
            formatValue={(v) => `$${v.toFixed(3)}`}
          />
        </div>
        <div className="analytics-panel analytics-panel-wide">
          <h3>Most Common Failures (Missed Steps)</h3>
          <BarList items={commonMissedSteps} defaultColor="var(--status-warning)" />
        </div>
      </div>
    </div>
  );
}

export default Analytics;
