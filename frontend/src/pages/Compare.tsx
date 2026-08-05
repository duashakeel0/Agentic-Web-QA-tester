import { useEffect, useState } from "react";
import BarList from "../components/charts/BarList";
import { apiGet, ApiError } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import type { ProviderStats } from "../types/history";
import "./Compare.css";

const ROWS: { label: string; get: (p: ProviderStats) => string; winner?: (a: ProviderStats, b: ProviderStats) => "claude" | "ollama" }[] = [
  { label: "Total Runs", get: (p) => `${p.run_count}` },
  { label: "Passed", get: (p) => `${p.pass_count}` },
  { label: "Failed", get: (p) => `${p.fail_count}` },
  {
    label: "Avg Latency",
    get: (p) => `${(p.avg_duration_ms / 1000).toFixed(1)}s`,
    winner: (a, b) => (a.avg_duration_ms <= b.avg_duration_ms ? "claude" : "ollama"),
  },
  {
    label: "Coverage",
    get: (p) => `${Math.round(p.avg_coverage_ratio * 100)}%`,
    winner: (a, b) => (a.avg_coverage_ratio >= b.avg_coverage_ratio ? "claude" : "ollama"),
  },
  {
    label: "Accuracy",
    get: (p) => `${Math.round(p.avg_accuracy_ratio * 100)}%`,
    winner: (a, b) => (a.avg_accuracy_ratio >= b.avg_accuracy_ratio ? "claude" : "ollama"),
  },
  {
    label: "Cost / Test",
    get: (p) => `$${p.avg_cost_usd.toFixed(4)}`,
    winner: (a, b) => (a.avg_cost_usd <= b.avg_cost_usd ? "claude" : "ollama"),
  },
  { label: "Total Cost", get: (p) => `$${p.total_cost_usd.toFixed(4)}` },
];

function Compare() {
  const { logout } = useAuth();
  const [stats, setStats] = useState<ProviderStats[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<ProviderStats[]>("/api/history/provider-stats")
      .then(setStats)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load comparison data.");
      });
  }, [logout]);

  const claude = stats?.find((p) => p.provider === "claude");
  const ollama = stats?.find((p) => p.provider === "ollama");

  const winCount = { claude: 0, ollama: 0 };
  if (claude && ollama) {
    for (const row of ROWS) {
      if (row.winner) {
        winCount[row.winner(claude, ollama)] += 1;
      }
    }
  }
  const overallWinner = winCount.claude === winCount.ollama ? null : winCount.claude > winCount.ollama ? "claude" : "ollama";

  return (
    <div className="compare-page">
      <h1 className="compare-title">Model Comparison</h1>
      <p className="compare-subtitle">Aggregated across every run each model has done so far.</p>

      {error && <p className="compare-error">{error}</p>}

      {!claude || !ollama ? (
        <p className="compare-empty">
          Not enough data yet - run at least one test with each model (or a "Compare Both" run) to see this page fill in.
        </p>
      ) : (
        <>
          <div className="compare-table-wrap">
            <table className="compare-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Claude (Sonnet 5)</th>
                  <th>Llama 3.1 (Ollama)</th>
                  <th>Winner</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => {
                  const winner = row.winner?.(claude, ollama);
                  return (
                    <tr key={row.label}>
                      <td className="compare-row-label">{row.label}</td>
                      <td className={winner === "claude" ? "compare-winner-cell" : ""}>{row.get(claude)}</td>
                      <td className={winner === "ollama" ? "compare-winner-cell" : ""}>{row.get(ollama)}</td>
                      <td className="compare-winner-tag">{winner ? (winner === "claude" ? "Claude" : "Ollama") : "—"}</td>
                    </tr>
                  );
                })}
                <tr className="compare-overall-row">
                  <td>Overall Winner</td>
                  <td colSpan={2}>
                    {overallWinner ? (overallWinner === "claude" ? "Claude (Sonnet 5)" : "Llama 3.1 (Ollama)") : "Tied"}
                  </td>
                  <td>{overallWinner && "🏆"}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="compare-missed-grid">
            <div className="compare-panel">
              <h3>Steps Claude Commonly Misses</h3>
              <BarList
                items={claude.common_missed_steps.map((m) => ({ label: m.step, value: m.count }))}
                defaultColor="var(--claude-color)"
              />
            </div>
            <div className="compare-panel">
              <h3>Steps Ollama Commonly Misses</h3>
              <BarList
                items={ollama.common_missed_steps.map((m) => ({ label: m.step, value: m.count }))}
                defaultColor="var(--ollama-color)"
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default Compare;
