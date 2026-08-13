import { useMockRun } from "../hooks/useMockRun";
import "./Dashboard.css";

function Dashboard() {
  const { result, error } = useMockRun();

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

export default Dashboard;
