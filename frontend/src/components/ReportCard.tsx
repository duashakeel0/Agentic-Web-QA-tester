import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Coins,
  Download,
  Gauge,
  Globe,
  Percent,
  Send,
  Terminal,
  Ticket,
  XCircle,
} from "lucide-react";
import { API_BASE_URL } from "../config";
import { downloadFile } from "../services/api";
import type { PipelineResult, Provider } from "../types/pipeline";
import "./ReportCard.css";

const PROVIDER_LABELS: Record<Provider, string> = { claude: "Claude", ollama: "Llama (Ollama)" };

function DownloadReportButton({ historyId, ticketId }: { historyId: number; ticketId: string }) {
  const [downloading, setDownloading] = useState(false);

  return (
    <button
      type="button"
      className="report-download-btn"
      disabled={downloading}
      onClick={async () => {
        setDownloading(true);
        try {
          await downloadFile(`/api/history/${historyId}/report.pdf`, `sentinelqa-report-${ticketId}-${historyId}.pdf`);
        } finally {
          setDownloading(false);
        }
      }}
    >
      <Download size={13} aria-hidden="true" />
      {downloading ? "Preparing…" : "Download Report"}
    </button>
  );
}

function ReportCard({ result, historyId }: { result: PipelineResult; historyId?: number }) {
  const [showActions, setShowActions] = useState(false);
  const { plan, exploration, verification, report, metrics } = result;

  if (!plan.matched) {
    return (
      <div className="report-card report-unmatched">
        <div className="report-header">
          <span className="report-badge report-badge-fail">
            <XCircle size={12} aria-hidden="true" /> NO MATCH
          </span>
          <span className="report-provider">{PROVIDER_LABELS[result.provider]}</span>
        </div>
        <div className="report-section">
          <p className="report-line">
            <Ticket size={13} aria-hidden="true" className="report-line-icon" />
            <strong>Ticket:</strong>&nbsp;{plan.ticket_id} {plan.ticket_title ? `- ${plan.ticket_title}` : ""}
          </p>
          <p className="report-reason">{plan.reason}</p>
        </div>
      </div>
    );
  }

  const verdict = verification?.verdict;
  const isPass = verdict === "pass";
  const isWarn = verdict === "pass_with_issues";
  const isFail = !isPass && !isWarn; // covers "fail" and a missing verification

  const cardClass = isFail ? "report-fail" : isWarn ? "report-warn" : "report-pass";
  const badgeClass = isFail ? "report-badge-fail" : isWarn ? "report-badge-warn" : "report-badge-pass";
  const badgeIcon = isFail ? (
    <XCircle size={12} aria-hidden="true" />
  ) : isWarn ? (
    <AlertTriangle size={12} aria-hidden="true" />
  ) : (
    <CheckCircle2 size={12} aria-hidden="true" />
  );
  const badgeLabel = isFail ? "FAIL" : isWarn ? "PASS WITH ISSUES" : "PASS";

  return (
    <div className={`report-card ${cardClass}`}>
      <div className="report-header">
        <span className={`report-badge ${badgeClass}`}>
          {badgeIcon}
          {badgeLabel}
        </span>
        <span className="report-provider">{PROVIDER_LABELS[result.provider]}</span>
        <span className="report-time">{(result.total_duration_ms / 1000).toFixed(1)}s total</span>
        {historyId !== undefined && <DownloadReportButton historyId={historyId} ticketId={result.ticket_id} />}
      </div>

      <div className="report-section report-overview">
        <p className="report-line">
          <Globe size={13} aria-hidden="true" className="report-line-icon" />
          <strong>Website tested:</strong>&nbsp;{plan.domain} ({plan.workflow})
        </p>
        <p className="report-line">
          <Ticket size={13} aria-hidden="true" className="report-line-icon" />
          <strong>Ticket:</strong>&nbsp;{plan.ticket_id} {plan.ticket_title ? `- ${plan.ticket_title}` : ""}
        </p>
      </div>

      {!isPass && report && report.findings.length > 0 && (
        <div className="report-section">
          <h4 className="report-section-title">Findings</h4>
          <div className="report-findings">
            {report.findings.map((finding, i) => (
              <div className={`finding-block finding-${finding.severity}`} key={i}>
                <span className="finding-severity">{finding.severity.toUpperCase()}</span>
                <p className="finding-line">
                  <strong>{isFail ? "Failed step:" : "Note:"}</strong>{" "}
                  {isFail ? (exploration?.error ?? finding.reproduction_steps.at(-1) ?? "n/a") : finding.summary}
                </p>
                {isFail && (
                  <p className="finding-line">
                    <strong>Failure reason:</strong> {finding.summary}
                  </p>
                )}
                {finding.error_message && (
                  <p className="finding-line">
                    <strong>Error message:</strong> {finding.error_message}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {isPass && (
        <div className="report-section">
          <p className="report-summary">
            <CheckCircle2 size={14} aria-hidden="true" className="report-line-icon" />
            Workflow completed and the expected outcome was verified.
          </p>
        </div>
      )}

      {metrics && (
        <div className="report-section report-metrics">
          <span>
            <Gauge size={12} aria-hidden="true" />
            {metrics.steps_covered}/{metrics.steps_planned} steps covered
          </span>
          <span>
            <Percent size={12} aria-hidden="true" />
            {Math.round(metrics.accuracy_ratio * 100)}% action accuracy
          </span>
          <span>
            <Terminal size={12} aria-hidden="true" />
            {metrics.llm_call_count} model calls
          </span>
          <span>
            <Coins size={12} aria-hidden="true" />${metrics.estimated_cost_usd.toFixed(4)} est. cost
          </span>
        </div>
      )}

      {report && (
        <p className="report-trello-status">
          <Send size={12} aria-hidden="true" />
          Trello comment:{" "}
          {report.post_summary_status === "posted"
            ? "posted"
            : report.post_summary_status === "failed"
              ? `failed (${report.post_summary_error})`
              : "pending"}
        </p>
      )}

      {exploration && exploration.actions.length > 0 && (
        <div className="report-actions-toggle">
          <button type="button" onClick={() => setShowActions((v) => !v)}>
            {showActions ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            {showActions ? "Hide" : "Show"} action log ({exploration.actions.length} action{exploration.actions.length === 1 ? "" : "s"})
          </button>
          {showActions && (
            <ul className="report-actions-list">
              {exploration.actions.map((action, i) => (
                <li key={i} className={action.success ? "action-success" : "action-fail"}>
                  {action.screenshot_path && (
                    <img
                      className="action-thumb"
                      src={`${API_BASE_URL}${action.screenshot_path}`}
                      alt={`${action.action} on ${action.step}`}
                    />
                  )}
                  <span className="action-text">
                    <span className="action-step">{action.step}</span>: {action.action}
                    {action.selector ? ` on ${action.selector}` : ""}
                    {action.value ? ` with ${JSON.stringify(action.value)}` : ""}
                    {!action.success && action.error ? ` — ${action.error}` : ""}
                  </span>
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
