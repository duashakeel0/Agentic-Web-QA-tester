import { useState } from "react";
import { useLiveRun } from "../hooks/useLiveRun";
import "./Dashboard.css";

function Dashboard() {
  const [url, setUrl] = useState("https://example.com");
  const { log, result, error, running, start } = useLiveRun();

  return (
    <div className="app">
      <h1>Agentic Web QA Tester</h1>
      <p className="subtitle">Day 2 — live browser driver over WebSocket</p>

      <div className="run-controls">
        <input
          type="text"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://example.com"
        />
        <button onClick={() => start(url)} disabled={running || !url}>
          {running ? "Running..." : "Run test"}
        </button>
      </div>

      {error && <p className="error">Could not complete run: {error}</p>}

      {log.length > 0 && (
        <div className="result-card">
          <p>
            <strong>Live log</strong>
          </p>
          <ul className="log-list">
            {log.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          {result && (
            <p className="summary">
              Loaded <strong>{result.url}</strong> — page title: "{result.title}"
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default Dashboard;
