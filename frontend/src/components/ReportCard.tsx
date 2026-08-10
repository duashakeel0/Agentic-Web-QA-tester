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
import type { ActionLogEntry, ExplorationResult, PipelineResult, Provider, TestPlan } from "../types/pipeline";
import DonutChart from "./charts/DonutChart";
import "./ReportCard.css";

const PROVIDER_LABELS: Record<Provider, string> = { claude: "Claude", ollama: "Llama (Ollama)" };

type StepStatus = "PASS" | "FAIL" | "SKIPPED" | "NOT REACHED";

interface StepRow {
  step: string;
  status: StepStatus;
  note: string;
}

/** One row per planned test step, derived entirely from the real action
 * log - mirrors backend/app/pdf_report.py's _step_rows() so the on-screen
 * report and the downloaded PDF agree on what happened. A step with no
 * actions at all is either "skipped" (already satisfied when the page
 * loaded, only possible for a completed run) or "not reached" (exploration
 * stopped before it). */
function buildStepRows(plan: TestPlan, exploration: ExplorationResult | undefined, verdict: string | undefined): StepRow[] {
  const actions = exploration?.actions ?? [];
  const completed = exploration?.completed ?? false;
  const realActions = actions.filter((a: ActionLogEntry) => !a.is_broken_input_attempt);
  // When the workflow ran to completion but the overall verdict is still
  // "fail", the expected outcome was never actually reached (e.g. a
  // login click succeeds mechanically, but the site never authenticates).
  // Every earlier step genuinely achieved its own local goal; it's
  // specifically the last real action taken - the one the final
  // assertion actually depends on - whose unqualified "PASS" reads as a
  // contradiction sitting right above a FAIL badge.
  const failedStep = completed && verdict === "fail" && realActions.length > 0
    ? realActions[realActions.length - 1].step
    : null;

  return plan.steps.map((step) => {
    const stepActions = actions.filter((a: ActionLogEntry) => a.step === step && !a.is_broken_input_attempt);
    if (stepActions.length === 0) {
      return completed
        ? { step, status: "SKIPPED", note: "Already satisfied when the page loaded - no action needed." }
        : { step, status: "NOT REACHED", note: "Exploration stopped before this step was attempted." };
    }
    if (step === failedStep) {
      return { step, status: "FAIL", note: "The action completed, but did not achieve the expected outcome - see Findings below." };
    }
    // A step's real outcome is whether it was ever actually achieved, not
    // whether its literal last logged attempt happened to succeed - a step
    // can (and often does) need a retry, and an unrelated hiccup on a
    // later, redundant attempt after the step already succeeded must
    // never flip a genuinely completed step to FAIL. Only "every attempt
    // failed" is a real failure for this step.
    if (stepActions.some((a) => a.success)) {
      return { step, status: "PASS", note: `Completed successfully in ${stepActions.length} action(s).` };
    }
    const last = stepActions[stepActions.length - 1];
    return { step, status: "FAIL", note: last.error ?? "Action failed with no further detail." };
  });
}

const STEP_STATUS_CLASS: Record<StepStatus, string> = {
  PASS: "step-status-pass",
  FAIL: "step-status-fail",
  SKIPPED: "step-status-skip",
  "NOT REACHED": "step-status-skip",
};

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
  // "ISSUE FOUND" rather than "FAIL" - by this point the agent has run
  // the workflow correctly and found a real defect on the site under
  // test, not failed to do its own job; see utils/verdict.ts.
  const badgeLabel = isFail ? "ISSUE FOUND" : isWarn ? "PASS WITH ISSUES" : "PASS";

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

      {metrics && metrics.actions_attempted > 0 && (
        <div className="report-section">
          <h4 className="report-section-title">Test Execution Summary</h4>
          <div className="report-summary-row">
            <DonutChart
              centerLabel="Actions passed"
              segments={[
                { label: "Passed", value: metrics.actions_succeeded, color: "var(--status-good)" },
                { label: "Failed", value: metrics.actions_attempted - metrics.actions_succeeded, color: "var(--status-critical)" },
              ]}
            />
            <dl className="report-summary-stats">
              <div>
                <dt>Total test steps</dt>
                <dd>{plan.steps.length}</dd>
              </div>
              <div>
                <dt>Steps covered</dt>
                <dd>
                  {metrics.steps_covered}/{metrics.steps_planned}
                </dd>
              </div>
              <div>
                <dt>Actions attempted</dt>
                <dd>{metrics.actions_attempted}</dd>
              </div>
              <div>
                <dt>Pass rate</dt>
                <dd>{Math.round(metrics.accuracy_ratio * 100)}%</dd>
              </div>
            </dl>
          </div>
        </div>
      )}

      {plan.steps.length > 0 && (
        <div className="report-section">
          <h4 className="report-section-title">Test Case Execution Details</h4>
          <div className="report-steps-table-wrap">
            <table className="report-steps-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Test Step</th>
                  <th>Status</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {buildStepRows(plan, exploration, verdict).map((row, i) => (
                  <tr key={i}>
                    <td>{i + 1}</td>
                    <td>{row.step}</td>
                    <td>
                      <span className={`step-status ${STEP_STATUS_CLASS[row.status]}`}>{row.status}</span>
                    </td>
                    <td className="report-steps-note">{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
