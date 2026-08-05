import { useEffect, useState } from "react";
import { Crown, Timer, Coins, Target, Percent, Trophy } from "lucide-react";
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

const PROVIDER_LABELS = { claude: "Claude", ollama: "Llama (Ollama)" } as const;

function MetricBar({
  icon: Icon,
  label,
  claude,
  ollama,
  claudeDisplay,
  ollamaDisplay,
  winner,
}: {
  icon: typeof Timer;
  label: string;
  claude: number;
  ollama: number;
  claudeDisplay: string;
  ollamaDisplay: string;
  winner: "claude" | "ollama" | null;
}) {
  // For "lower is better" metrics (latency, cost) the bar still encodes
  // magnitude directly - the winner badge (not bar length) communicates
  // which direction is good, so the visualization stays honest either way.
  const max = Math.max(claude, ollama, 0.0001);

  return (
    <div className="compare-metric-bar">
      <div className="compare-metric-bar-label">
        <Icon size={14} aria-hidden="true" />
        {label}
      </div>
      <div className="compare-metric-bar-row">
        <span className="compare-metric-bar-provider">Claude</span>
        <div className="compare-metric-bar-track">
          <div className="compare-metric-bar-fill compare-metric-bar-claude" style={{ width: `${(claude / max) * 100}%` }} />
        </div>
        <span className="compare-metric-bar-value">
          {claudeDisplay}
          {winner === "claude" && <Crown size={12} className="compare-metric-crown" aria-label="Winner" />}
        </span>
      </div>
      <div className="compare-metric-bar-row">
        <span className="compare-metric-bar-provider">Ollama</span>
        <div className="compare-metric-bar-track">
          <div className="compare-metric-bar-fill compare-metric-bar-ollama" style={{ width: `${(ollama / max) * 100}%` }} />
        </div>
        <span className="compare-metric-bar-value">
          {ollamaDisplay}
          {winner === "ollama" && <Crown size={12} className="compare-metric-crown" aria-label="Winner" />}
        </span>
      </div>
    </div>
  );
}

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
      <p className="compare-subtitle">Claude vs Llama (Ollama), aggregated across every run each model has done so far.</p>

      {error && <p className="compare-error">{error}</p>}

      {!claude || !ollama ? (
        <div className="compare-empty">
          <Trophy size={26} aria-hidden="true" />
          <p>
            Not enough data yet — run at least one test with each model (or a "Compare Both" run) to see this page fill in.
          </p>
        </div>
      ) : (
        <>
          {overallWinner && (
            <div className={`compare-winner-banner compare-winner-banner-${overallWinner}`}>
              <Trophy size={18} aria-hidden="true" />
              <span>
                <strong>{PROVIDER_LABELS[overallWinner]}</strong> leads on {winCount[overallWinner]} of{" "}
                {winCount.claude + winCount.ollama} scored metrics.
              </span>
            </div>
          )}

          <div className="compare-bars-grid">
            <MetricBar
              icon={Timer}
              label="Avg Latency"
              claude={claude.avg_duration_ms}
              ollama={ollama.avg_duration_ms}
              claudeDisplay={`${(claude.avg_duration_ms / 1000).toFixed(1)}s`}
              ollamaDisplay={`${(ollama.avg_duration_ms / 1000).toFixed(1)}s`}
              winner={claude.avg_duration_ms <= ollama.avg_duration_ms ? "claude" : "ollama"}
            />
            <MetricBar
              icon={Target}
              label="Coverage"
              claude={claude.avg_coverage_ratio}
              ollama={ollama.avg_coverage_ratio}
              claudeDisplay={`${Math.round(claude.avg_coverage_ratio * 100)}%`}
              ollamaDisplay={`${Math.round(ollama.avg_coverage_ratio * 100)}%`}
              winner={claude.avg_coverage_ratio >= ollama.avg_coverage_ratio ? "claude" : "ollama"}
            />
            <MetricBar
              icon={Percent}
              label="Accuracy"
              claude={claude.avg_accuracy_ratio}
              ollama={ollama.avg_accuracy_ratio}
              claudeDisplay={`${Math.round(claude.avg_accuracy_ratio * 100)}%`}
              ollamaDisplay={`${Math.round(ollama.avg_accuracy_ratio * 100)}%`}
              winner={claude.avg_accuracy_ratio >= ollama.avg_accuracy_ratio ? "claude" : "ollama"}
            />
            <MetricBar
              icon={Coins}
              label="Cost / Test"
              claude={claude.avg_cost_usd}
              ollama={ollama.avg_cost_usd}
              claudeDisplay={`$${claude.avg_cost_usd.toFixed(4)}`}
              ollamaDisplay={`$${ollama.avg_cost_usd.toFixed(4)}`}
              winner={claude.avg_cost_usd <= ollama.avg_cost_usd ? "claude" : "ollama"}
            />
          </div>

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
                      <td className="compare-winner-tag">{winner ? PROVIDER_LABELS[winner] : "—"}</td>
                    </tr>
                  );
                })}
                <tr className="compare-overall-row">
                  <td>Overall Winner</td>
                  <td colSpan={2}>{overallWinner ? PROVIDER_LABELS[overallWinner] : "Tied"}</td>
                  <td>{overallWinner && <Trophy size={14} aria-hidden="true" />}</td>
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
