import { useEffect, useState } from "react";
import "./App.css";

interface TestRunResult {
  status: string;
  pages_visited: number;
  actions_taken: number;
  bugs_found: number;
  summary: string;
}

const API_BASE = "http://localhost:8000/api";

function App() {
  const [result, setResult] = useState<TestRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/mock-run`)
      .then((res) => {
        if (!res.ok) throw new Error(`Backend returned ${res.status}`);
        return res.json();
      })
      .then(setResult)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div className="app">
      <h1>Agentic Web QA Tester</h1>
      <p className="subtitle">Day 1 scaffold — mock end-to-end stub</p>

      {error && <p className="error">Could not reach backend: {error}</p>}

      {!error && !result && <p>Loading mock run...</p>}

      {result && (
        <div className="result-card">
          <p>
            <strong>Status:</strong> {result.status}
          </p>
          <p>
            <strong>Pages visited:</strong> {result.pages_visited}
          </p>
          <p>
            <strong>Actions taken:</strong> {result.actions_taken}
          </p>
          <p>
            <strong>Bugs found:</strong> {result.bugs_found}
          </p>
          <p className="summary">{result.summary}</p>
        </div>
      )}
    </div>
  );
}

export default App;
