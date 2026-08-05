import { useState } from "react";
import type { PipelineResult, Provider } from "../types/pipeline";
import "./ReportCard.css";

const PROVIDER_LABELS: Record<Provider, string> = { claude: "Claude", ollama: "Llama (Ollama)" };

function ReportCard({ result }: { result: PipelineResult }) {
  const [showActions, setShowActions] = useState(false);
  const { plan, exploration, verification, report, metrics } = result;

  if (!plan.matched) {
    return (
      <div className="report-card report-unmatched">
        <div className="report-header">
          <span className="report-badge report-badge-fail">NO MATCH</span>
          <span className="report-provider">{PROVIDER_LABELS[result.provider]}</span>
        </div>
        <p className="report-line">
          <strong>Ticket:</strong> {plan.ticket_id} {plan.ticket_title ? `- ${plan.ticket_title}` : ""}
        </p>
        <p className="report-reason">{plan.reason}</p>
      </div>
    );
  }

  const passed = verification?.verdict === "pass";

  return (
    <div className={`report-card ${passed ? "report-pass" : "report-fail"}`}>
      <div className="report-header">
        <span className={`report-badge ${passed ? "report-badge-pass" : "report-badge-fail"}`}>
          {passed ? "PASS" : "FAIL"}
        </span>
        <span className="report-provider">{PROVIDER_LABELS[result.provider]}</span>
        <span className="report-time">{(result.total_duration_ms / 1000).toFixed(1)}s total</span>
      </div>

      <p className="report-line">
        <strong>Website tested:</strong> {plan.domain} ({plan.workflow})
      </p>
      <p className="report-line">
        <strong>Ticket:</strong> {plan.ticket_id} {plan.ticket_title ? `- ${plan.ticket_title}` : ""}
      </p>

      {!passed && report && report.findings.length > 0 && (
        <div className="report-findings">
          {report.findings.map((finding, i) => (
            <div className={`finding-block finding-${finding.severity}`} key={i}>
              <span className="finding-severity">{finding.severity.toUpperCase()}</span>
              <p className="finding-line">
                <strong>Failed step:</strong> {exploration?.error ?? finding.reproduction_steps.at(-1) ?? "n/a"}
              </p>
              <p className="finding-line">
                <strong>Failure reason:</strong> {finding.summary}
              </p>
              {finding.error_message && (
                <p className="finding-line">
                  <strong>Error message:</strong> {finding.error_message}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {passed && <p className="report-summary">Workflow completed and the expected outcome was verified.</p>}

      {metrics && (
        <div className="report-metrics">
          <span>{metrics.steps_covered}/{metrics.steps_planned} steps covered</span>
          <span>{Math.round(metrics.accuracy_ratio * 100)}% action accuracy</span>
          <span>{metrics.llm_call_count} model calls</span>
          <span>${metrics.estimated_cost_usd.toFixed(4)} est. cost</span>
        </div>
      )}

      {report && (
        <p className="report-trello-status">
          Trello comment: {report.post_summary_status === "posted" ? "posted ✔" : report.post_summary_status === "failed" ? `failed (${report.post_summary_error})` : "pending"}
        </p>
      )}

      {exploration && exploration.actions.length > 0 && (
        <div className="report-actions-toggle">
          <button type="button" onClick={() => setShowActions((v) => !v)}>
            {showActions ? "Hide" : "Show"} agent outputs ({exploration.actions.length} action(s))
          </button>
          {showActions && (
            <ul className="report-actions-list">
              {exploration.actions.map((action, i) => (
                <li key={i} className={action.success ? "action-success" : "action-fail"}>
                  <span className="action-step">{action.step}</span>: {action.action}
                  {action.selector ? ` on ${action.selector}` : ""}
                  {action.value ? ` with ${JSON.stringify(action.value)}` : ""}
                  {!action.success && action.error ? ` — ${action.error}` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default ReportCard;
