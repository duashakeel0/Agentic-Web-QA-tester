import { useState } from "react";
import { useLiveRun } from "../hooks/useLiveRun";
import "./Dashboard.css";

function Dashboard() {
  const [url, setUrl] = useState("https://example.com");
  const { log, result, error, running, start } = useLiveRun();

  const status = error ? "error" : running ? "running" : result ? "done" : "idle";
  const statusLabel = { idle: "Idle", running: "Running", done: "Done", error: "Error" }[status];

  return (
    <div className="page">
      <header className="hero">
        <span className="eyebrow">Day 2 — Browser Driver</span>
        <h1>Live Browser Test Runner</h1>
        <p className="subtitle">
          Point it at a URL and watch a real browser get driven live over a WebSocket.
        </p>
      </header>

      <div className="panel">
        <form
          className="run-controls"
          onSubmit={(event) => {
            event.preventDefault();
            start(url);
          }}
        >
          <input
            type="text"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com"
          />
          <button type="submit" disabled={running || !url}>
            {running ? "Running…" : "Run test"}
          </button>
        </form>

        <div className="status-row">
          <span className={`status-dot status-${status}`} />
          <span className="status-label">{statusLabel}</span>
        </div>

        {error && <p className="error">Could not complete run: {error}</p>}

        {log.length > 0 && (
          <div className="log-console">
            {log.map((line, index) => (
              <div className="log-line" key={`${index}-${line}`}>
                <span className="log-arrow">→</span> {line}
              </div>
            ))}
          </div>
        )}

        {result && (
          <div className="result-card">
            <span className="result-label">Loaded page</span>
            <p className="result-url">{result.url}</p>
            <p className="result-title">"{result.title}"</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
