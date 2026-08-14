import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Clock, PlayCircle, RefreshCw } from "lucide-react";
import { apiGet, apiPost, ApiError } from "../services/api";
import "./Scheduler.css";

interface SmokeWorkflowOut {
  domain: string;
  workflow: string;
}

interface SmokeCycleErrorOut {
  domain: string;
  workflow: string;
  error: string;
}

interface SmokeCycleOut {
  triggered_by: string;
  provider: string;
  started_at: number;
  finished_at: number;
  pass_count: number;
  fail_count: number;
  run_ids: number[];
  errors: SmokeCycleErrorOut[];
}

interface SchedulerStatus {
  enabled: boolean;
  interval_minutes: number;
  provider: string;
  next_run_at: number | null;
  smoke_workflows: SmokeWorkflowOut[];
  last_cycle: SmokeCycleOut | null;
}

function formatTimestamp(seconds: number | null): string {
  if (seconds === null) return "—";
  return new Date(seconds * 1000).toLocaleString();
}

function groupByDomain(workflows: SmokeWorkflowOut[]): Record<string, string[]> {
  const grouped: Record<string, string[]> = {};
  for (const w of workflows) {
    grouped[w.domain] = grouped[w.domain] ?? [];
    grouped[w.domain].push(w.workflow);
  }
  return grouped;
}

function Scheduler() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    apiGet<SchedulerStatus>("/api/scheduler/status")
      .then((data) => {
        setStatus(data);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Could not load scheduler status."))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleRunNow() {
    setRunning(true);
    setRunError(null);
    try {
      // Same execution path as the scheduled tick - this endpoint calls
      // the exact same run_cycle() the interval timer calls, just
      // triggered by a button instead of the clock.
      await apiPost<SmokeCycleOut>("/api/scheduler/run-now", {});
      load();
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "Smoke run failed to start.");
    } finally {
      setRunning(false);
    }
  }

  const grouped = status ? groupByDomain(status.smoke_workflows) : {};
  const cycle = status?.last_cycle ?? null;

  return (
    <div className="scheduler-page">
      <div className="scheduler-header">
        <div>
          <h1 className="scheduler-title">Scheduled Testing</h1>
          <p className="scheduler-subtitle">
            A small subset of each domain's workflows run unattended on a fixed interval to catch regressions before a
            real ticket ever surfaces them - independent of any ticket. Trigger a cycle on demand below; it runs the
            exact same code path as the scheduled tick.
          </p>
        </div>
        <button type="button" className="scheduler-run-now" onClick={handleRunNow} disabled={running}>
          {running ? <RefreshCw size={15} className="spin" /> : <PlayCircle size={15} />}
          {running ? "Running smoke cycle…" : "Run Smoke Tests Now"}
        </button>
      </div>

      {loading && <p className="scheduler-empty">Loading…</p>}
      {loadError && <p className="scheduler-error">{loadError}</p>}
      {runError && <p className="scheduler-error">{runError}</p>}

      {status && (
        <>
          <div className="scheduler-stat-row">
            <div className="scheduler-stat-card">
              <Clock size={15} aria-hidden="true" />
              <div>
                <div className="scheduler-stat-label">Status</div>
                <div className="scheduler-stat-value">{status.enabled ? "Running" : "Stopped"}</div>
              </div>
            </div>
            <div className="scheduler-stat-card">
              <div>
                <div className="scheduler-stat-label">Interval</div>
                <div className="scheduler-stat-value">Every {status.interval_minutes} min</div>
              </div>
            </div>
            <div className="scheduler-stat-card">
              <div>
                <div className="scheduler-stat-label">Next run</div>
                <div className="scheduler-stat-value">{formatTimestamp(status.next_run_at)}</div>
              </div>
            </div>
            <div className="scheduler-stat-card">
              <div>
                <div className="scheduler-stat-label">Provider</div>
                <div className="scheduler-stat-value">{status.provider}</div>
              </div>
            </div>
          </div>

          <section className="scheduler-panel">
            <h2 className="scheduler-panel-title">Smoke workflows by domain</h2>
            {Object.keys(grouped).length === 0 && (
              <p className="scheduler-empty">No workflows are flagged for smoke testing yet.</p>
            )}
            <div className="scheduler-domain-list">
              {Object.entries(grouped).map(([domain, workflows]) => (
                <div className="scheduler-domain-card" key={domain}>
                  <div className="scheduler-domain-name">{domain}</div>
                  <ul className="scheduler-workflow-list">
                    {workflows.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>

          <section className="scheduler-panel">
            <h2 className="scheduler-panel-title">Last cycle</h2>
            {!cycle && <p className="scheduler-empty">No smoke cycle has run yet.</p>}
            {cycle && (
              <div className="scheduler-cycle">
                <div className="scheduler-cycle-summary">
                  <span className={`scheduler-badge ${cycle.triggered_by === "scheduled" ? "badge-scheduled" : "badge-on-demand"}`}>
                    {cycle.triggered_by === "scheduled" ? "Scheduled" : "On-demand"}
                  </span>
                  <span className="scheduler-cycle-time">{formatTimestamp(cycle.started_at)}</span>
                  <span className="scheduler-cycle-counts">
                    <span className="count-pass">{cycle.pass_count} passed</span>
                    {" · "}
                    <span className="count-fail">{cycle.fail_count} failed</span>
                  </span>
                </div>
                {cycle.errors.length > 0 && (
                  <ul className="scheduler-cycle-errors">
                    {cycle.errors.map((e, i) => (
                      <li key={i}>
                        <strong>
                          {e.domain}/{e.workflow}
                        </strong>
                        : {e.error}
                      </li>
                    ))}
                  </ul>
                )}
                {cycle.run_ids.length > 0 && (
                  <div className="scheduler-cycle-links">
                    {cycle.run_ids.map((id) => (
                      <Link key={id} to={`/history/${id}`} className="scheduler-cycle-link">
                        View run #{id}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

export default Scheduler;
