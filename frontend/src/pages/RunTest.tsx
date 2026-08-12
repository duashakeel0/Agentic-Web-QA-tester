import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, KeyRound, Rocket, RotateCcw } from "lucide-react";
import ComparisonSummary from "../components/ComparisonSummary";
import LiveBrowserView from "../components/LiveBrowserView";
import ModelSelector from "../components/ModelSelector";
import PipelineTimeline from "../components/PipelineTimeline";
import ReportCard from "../components/ReportCard";
import TalkingAgentsPanel from "../components/TalkingAgentsPanel";
import { usePipelineRunContext } from "../contexts/PipelineRunContext";
import { apiGet } from "../services/api";
import type { ModelChoice, Provider } from "../types/pipeline";
import "./RunTest.css";

// Claude first, then Ollama - the order the combined report reads in: each
// provider's full report, then the comparison beneath both.
const PROVIDER_ORDER: Provider[] = ["claude", "ollama"];

interface TrelloStatus {
  connected: boolean;
}

function RunTest() {
  const [ticketId, setTicketId] = useState("");
  const [model, setModel] = useState<ModelChoice>("claude");
  const { status, feed, stages, frames, frameHistory, results, comparison, errorMessage, start, reset } =
    usePipelineRunContext();

  // Every ticket run reads its details from Trello, so there's no point
  // letting someone submit a ticket ID before that's set up - checked
  // once up front rather than only finding out after the backend rejects
  // the run, which would otherwise be the first sign anything was wrong.
  const [trelloConnected, setTrelloConnected] = useState<boolean | null>(null);
  useEffect(() => {
    apiGet<TrelloStatus>("/api/trello/status")
      .then((data) => setTrelloConnected(data.connected))
      .catch(() => setTrelloConnected(null));
  }, []);

  const running = status === "connecting" || status === "running";
  const resultList = PROVIDER_ORDER.map((p) => results[p]).filter((r) => r !== undefined);
  const needsTrello = trelloConnected === false;

  return (
    <div className="run-test-page">
      <h1 className="run-test-title">Run a Test</h1>
      <p className="run-test-subtitle">
        Enter a Trello ticket ID for a registered website and pick which model(s) should drive the agents.
      </p>

      {needsTrello && (
        <div className="run-test-connect-trello">
          <KeyRound size={16} aria-hidden="true" />
          <span>
            Trello isn't connected yet - every ticket run reads its details from Trello, so connect it before
            running one.
          </span>
          <Link to="/trello-settings" className="run-test-connect-trello-link">
            Connect Trello
          </Link>
        </div>
      )}

      <div className="run-test-panel">
        <form
          className="run-test-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (ticketId.trim() && !needsTrello) start(ticketId.trim(), model);
          }}
        >
          <label className="run-test-field">
            <span>Trello ticket ID</span>
            <input
              type="text"
              value={ticketId}
              onChange={(event) => setTicketId(event.target.value)}
              placeholder="e.g. 66f2a1b3c9d4e5f6a7b8c9d0"
              disabled={running || needsTrello}
            />
          </label>

          <ModelSelector value={model} onChange={setModel} disabled={running || needsTrello} />

          <div className="run-test-actions">
            <button type="submit" disabled={running || needsTrello || !ticketId.trim()}>
              <Rocket size={16} aria-hidden="true" />
              {running ? "Running…" : "Start Test"}
            </button>
            {status !== "idle" && (
              <button type="button" className="run-test-reset" onClick={reset} disabled={running}>
                <RotateCcw size={13} aria-hidden="true" />
                Reset
              </button>
            )}
          </div>
        </form>

        {status !== "idle" && (
          <div className="run-test-status-row">
            <span className={`status-dot status-${status}`} />
            <span>
              {status === "connecting" && "Connecting…"}
              {status === "running" && "Agents are working…"}
              {status === "done" && "Run complete."}
              {status === "error" && "Run failed."}
            </span>
          </div>
        )}

        {errorMessage && (
          <div className="run-test-error">
            <AlertTriangle size={14} aria-hidden="true" />
            {errorMessage}
          </div>
        )}
      </div>

      {status !== "idle" && (
        <div className="run-test-live">
          <div className="run-test-live-column">
            <h2 className="run-test-section-title">Timeline</h2>
            <PipelineTimeline stages={stages} />
          </div>
          <div className="run-test-live-column run-test-live-column-wide">
            <h2 className="run-test-section-title">Talking Agents</h2>
            <TalkingAgentsPanel feed={feed} showProvider={Object.keys(stages).length > 1} />
          </div>
        </div>
      )}

      {Object.keys(stages).length > 0 && (
        <div className="run-test-browsers">
          {Object.keys(stages).map((p) => (
            <LiveBrowserView
              provider={p as Provider}
              frame={frames[p as Provider]}
              history={frameHistory[p as Provider] ?? []}
              key={p}
            />
          ))}
        </div>
      )}

      {resultList.length > 0 && (
        <div className="run-test-reports">
          <h2 className="run-test-section-title">{resultList.length > 1 ? "Full Comparison Report" : "Report"}</h2>
          <div className="run-test-report-stack">
            {resultList.map((result) => (
              <ReportCard result={result} key={result.provider} />
            ))}
            {comparison && (
              <ComparisonSummary comparison={comparison} claudeResult={results.claude} ollamaResult={results.ollama} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default RunTest;
