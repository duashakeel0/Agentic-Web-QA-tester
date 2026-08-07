import type { ComparisonReport } from "../types/pipeline";
import "./ComparisonSummary.css";

function ComparisonSummary({ comparison }: { comparison: ComparisonReport }) {
  const rows: { label: string; claude: string; ollama: string; winner?: "claude" | "ollama" }[] = [
    {
      label: "Verdict",
      claude: comparison.claude_verdict?.toUpperCase() ?? "n/a",
      ollama: comparison.ollama_verdict?.toUpperCase() ?? "n/a",
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
