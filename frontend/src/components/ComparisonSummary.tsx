import BarList from "./charts/BarList";
import { API_BASE_URL } from "../config";
import type { ComparisonReport, PipelineResult } from "../types/pipeline";
import "./ComparisonSummary.css";

/** The last screenshot captured for a run - a same-point-in-time "final
 * state" shot, useful for an at-a-glance side-by-side even though each
 * provider's own report above already has the full action-by-action log. */
function finalScreenshot(result: PipelineResult | null | undefined): string | null {
  const actions = result?.exploration?.actions ?? [];
  for (let i = actions.length - 1; i >= 0; i -= 1) {
    if (actions[i].screenshot_path) return actions[i].screenshot_path;
  }
  return null;
}

function ComparisonSummary({
  comparison,
  claudeResult,
  ollamaResult,
}: {
  comparison: ComparisonReport;
  claudeResult?: PipelineResult | null;
  ollamaResult?: PipelineResult | null;
}) {
  const claudeShot = finalScreenshot(claudeResult);
  const ollamaShot = finalScreenshot(ollamaResult);

  const chartItems = [
    {
      label: "Claude Coverage",
      value: Math.round((comparison.claude_metrics?.coverage_ratio ?? 0) * 100),
      color: "var(--claude-color)",
    },
    {
      label: "Ollama Coverage",
      value: Math.round((comparison.ollama_metrics?.coverage_ratio ?? 0) * 100),
      color: "var(--ollama-color)",
    },
    {
      label: "Claude Accuracy",
      value: Math.round((comparison.claude_metrics?.accuracy_ratio ?? 0) * 100),
      color: "var(--claude-color)",
    },
    {
      label: "Ollama Accuracy",
      value: Math.round((comparison.ollama_metrics?.accuracy_ratio ?? 0) * 100),
      color: "var(--ollama-color)",
    },
  ];

  const rows: { label: string; claude: string; ollama: string; winner?: "claude" | "ollama" }[] = [
    {
      label: "Verdict",
      claude: comparison.claude_verdict?.replace(/_/g, " ").toUpperCase() ?? "n/a",
      ollama: comparison.ollama_verdict?.replace(/_/g, " ").toUpperCase() ?? "n/a",
    },
    {
      label: "Time taken",
      claude: `${(comparison.claude_total_duration_ms / 1000).toFixed(1)}s`,
      ollama: `${(comparison.ollama_total_duration_ms / 1000).toFixed(1)}s`,
      winner: comparison.faster_provider ?? undefined,
    },
    {
      label: "Estimated cost",
      claude: `$${(comparison.claude_metrics?.estimated_cost_usd ?? 0).toFixed(4)}`,
      ollama: "$0.0000 (local)",
      winner: comparison.cheaper_provider ?? undefined,
    },
    {
      label: "Coverage",
      claude: `${Math.round((comparison.claude_metrics?.coverage_ratio ?? 0) * 100)}%`,
      ollama: `${Math.round((comparison.ollama_metrics?.coverage_ratio ?? 0) * 100)}%`,
      winner: comparison.better_coverage_provider ?? undefined,
    },
    {
      label: "Accuracy",
      claude: `${Math.round((comparison.claude_metrics?.accuracy_ratio ?? 0) * 100)}%`,
      ollama: `${Math.round((comparison.ollama_metrics?.accuracy_ratio ?? 0) * 100)}%`,
      winner: comparison.more_accurate_provider ?? undefined,
    },
    {
      label: "Findings",
      claude: `${comparison.claude_findings_count}`,
      ollama: `${comparison.ollama_findings_count}`,
    },
  ];

  return (
    <div className="comparison-summary">
      <h3 className="comparison-title">Claude vs Ollama</h3>

      {(claudeShot || ollamaShot) && (
        <div className="comparison-screenshots">
          <div className="comparison-screenshot-block">
            <span className="comparison-screenshot-label">Claude - final state</span>
            {claudeShot ? (
              <img src={`${API_BASE_URL}${claudeShot}`} alt="Claude run - final page state" />
            ) : (
              <div className="comparison-screenshot-empty">No screenshot</div>
            )}
          </div>
          <div className="comparison-screenshot-block">
            <span className="comparison-screenshot-label">Ollama - final state</span>
            {ollamaShot ? (
              <img src={`${API_BASE_URL}${ollamaShot}`} alt="Ollama run - final page state" />
            ) : (
              <div className="comparison-screenshot-empty">No screenshot</div>
            )}
          </div>
        </div>
      )}

      <div className="comparison-chart">
        <BarList items={chartItems} />
      </div>

      <div className="comparison-table">
        <div className="comparison-row comparison-head">
          <span />
          <span>Claude</span>
          <span>Llama (Ollama)</span>
        </div>
        {rows.map((row) => (
          <div className="comparison-row" key={row.label}>
            <span className="comparison-row-label">{row.label}</span>
            <span className={row.winner === "claude" ? "comparison-winner" : ""}>{row.claude}</span>
            <span className={row.winner === "ollama" ? "comparison-winner" : ""}>{row.ollama}</span>
          </div>
        ))}
      </div>

      {(comparison.missed_only_by_claude.length > 0 || comparison.missed_only_by_ollama.length > 0) && (
        <div className="comparison-missed">
          {comparison.missed_only_by_claude.length > 0 && (
            <p>
              <strong>Only Claude missed:</strong> {comparison.missed_only_by_claude.join(", ")}
            </p>
          )}
          {comparison.missed_only_by_ollama.length > 0 && (
            <p>
              <strong>Only Ollama missed:</strong> {comparison.missed_only_by_ollama.join(", ")}
            </p>
          )}
        </div>
      )}

      <p className="comparison-narrative">{comparison.summary}</p>
    </div>
  );
}

export default ComparisonSummary;
