import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiGet, ApiError } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import type { HistoryEntry } from "../types/history";
import "./History.css";

const PAGE_SIZE = 15;

function formatDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function History() {
  const { logout } = useAuth();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState<"" | "claude" | "ollama">("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    (currentOffset: number, currentSearch: string, currentProvider: string) => {
      setLoading(true);
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(currentOffset) });
      if (currentSearch.trim()) params.set("search", currentSearch.trim());
      if (currentProvider) params.set("provider", currentProvider);

      apiGet<HistoryEntry[]>(`/api/history?${params.toString()}`)
        .then((data) => {
          setEntries(data);
          setError(null);
        })
        .catch((err) => {
          if (err instanceof ApiError && err.status === 401) {
            logout();
            return;
          }
          setError(err instanceof Error ? err.message : "Could not load history.");
        })
        .finally(() => setLoading(false));
    },
    [logout],
  );

  useEffect(() => {
    load(offset, search, provider);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, provider]);

  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    load(0, search, provider);
  }

  return (
    <div className="history-page">
      <h1 className="history-title">History</h1>
      <p className="history-subtitle">Every test your AI QA agents have run, searchable by ticket or website.</p>

      <form className="history-controls" onSubmit={handleSearchSubmit}>
        <input
          type="text"
          placeholder="Search by ticket ID or website…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select
          value={provider}
          onChange={(event) => {
            setProvider(event.target.value as "" | "claude" | "ollama");
            setOffset(0);
          }}
        >
          <option value="">All models</option>
          <option value="claude">Claude</option>
          <option value="ollama">Ollama</option>
        </select>
        <button type="submit">Search</button>
      </form>

      {error && <p className="history-error">{error}</p>}

      <div className="history-table-wrap">
        <table className="history-table">
          <thead>
            <tr>
              <th>Website</th>
              <th>Ticket</th>
              <th>Model</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Findings</th>
              <th>Date</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {!loading && entries.length === 0 && (
              <tr>
                <td colSpan={8} className="history-empty">
                  No runs found.
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{entry.matched ? `${entry.domain}/${entry.workflow}` : "unmatched"}</td>
                <td className="history-ticket">{entry.ticket_id}</td>
                <td>
                  <span className={`history-provider-tag history-provider-${entry.provider}`}>{entry.provider}</span>
                </td>
                <td>
                  {entry.matched ? (
                    <span className={`history-status history-status-${entry.verdict}`}>{entry.verdict?.toUpperCase()}</span>
                  ) : (
                    <span className="history-status history-status-unmatched">NO MATCH</span>
                  )}
                </td>
                <td>{(entry.total_duration_ms / 1000).toFixed(1)}s</td>
                <td>{entry.findings_count}</td>
                <td>{formatDate(entry.created_at)}</td>
                <td>
                  <Link className="history-view-link" to={`/history/${entry.id}`}>
                    View Report
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="history-pagination">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Previous
        </button>
        <button type="button" disabled={entries.length < PAGE_SIZE} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Next
        </button>
      </div>
    </div>
  );
}

export default History;
