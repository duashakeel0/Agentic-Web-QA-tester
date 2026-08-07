import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowUpDown,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  FileSearch,
  Search,
} from "lucide-react";
import { apiGet, ApiError } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import type { HistoryEntry } from "../types/history";
import "./History.css";

const PAGE_SIZE = 15;

type SortKey = "duration" | "findings" | "date";
type SortDir = "asc" | "desc";

const PROVIDER_FILTERS: { value: "" | "claude" | "ollama"; label: string }[] = [
  { value: "", label: "All models" },
  { value: "claude", label: "Claude" },
  { value: "ollama", label: "Llama (Ollama)" },
];

function formatDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  });
}

function History() {
  const { logout } = useAuth();
  const [searchParams] = useSearchParams();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [searchInput, setSearchInput] = useState(() => searchParams.get("search") ?? "");
  const [committedSearch, setCommittedSearch] = useState(() => searchParams.get("search") ?? "");
  const [provider, setProvider] = useState<"" | "claude" | "ollama">("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");

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

  // Picks up a search term arriving from outside this page (the topbar
  // search bar navigates here with ?search=...) even if History is already
  // mounted, not just on first load.
  useEffect(() => {
    const urlSearch = searchParams.get("search") ?? "";
    setSearchInput(urlSearch);
    setCommittedSearch(urlSearch);
    setOffset(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.toString()]);

  useEffect(() => {
    load(offset, committedSearch, provider);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, provider, committedSearch]);

  function handleSearchSubmit(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setCommittedSearch(searchInput);
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const sortedEntries = useMemo(() => {
    if (!sortKey) return entries;
    const copy = [...entries];
    const value = (e: HistoryEntry) =>
      sortKey === "duration" ? e.total_duration_ms : sortKey === "findings" ? e.findings_count : e.created_at;
    copy.sort((a, b) => (value(a) - value(b)) * (sortDir === "asc" ? 1 : -1));
    return copy;
  }, [entries, sortKey, sortDir]);

  function SortHeader({ label, sortKeyName }: { label: string; sortKeyName: SortKey }) {
    const active = sortKey === sortKeyName;
    return (
      <button type="button" className={`history-sort-btn${active ? " active" : ""}`} onClick={() => toggleSort(sortKeyName)}>
        {label}
        {active ? sortDir === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} /> : <ArrowUpDown size={11} />}
      </button>
    );
  }

  const hasActiveFilters = committedSearch.trim() !== "" || provider !== "";

  return (
    <div className="history-page">
      <h1 className="history-title">Test History</h1>
      <p className="history-subtitle">Every test your AI QA agents have run, searchable by ticket or website.</p>

      <form className="history-controls" onSubmit={handleSearchSubmit}>
        <div className="history-search-field">
          <Search size={15} aria-hidden="true" />
          <input
            type="text"
            placeholder="Search by ticket ID or website…"
            aria-label="Search test history"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
          />
        </div>
        <div className="history-provider-chips" role="group" aria-label="Filter by model">
          {PROVIDER_FILTERS.map((f) => (
            <button
              key={f.value || "all"}
              type="button"
              className={`history-chip${provider === f.value ? " active" : ""}`}
              onClick={() => {
                setProvider(f.value);
                setOffset(0);
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button type="submit" className="history-search-submit">
          Search
        </button>
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
              <th>
                <SortHeader label="Duration" sortKeyName="duration" />
              </th>
              <th>
                <SortHeader label="Issues" sortKeyName="findings" />
              </th>
              <th>
                <SortHeader label="Timestamp" sortKeyName="date" />
              </th>
              <th />
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={`skeleton-${i}`} className="history-skeleton-row">
                  <td colSpan={8}>
                    <div className="history-skeleton-bar" />
                  </td>
                </tr>
              ))}
            {!loading && sortedEntries.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <div className="history-empty">
                    <FileSearch size={26} aria-hidden="true" />
                    <p>{hasActiveFilters ? "No runs match your filters." : "No tests run yet."}</p>
                  </div>
                </td>
              </tr>
            )}
            {!loading &&
              sortedEntries.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.matched ? `${entry.domain}/${entry.workflow}` : "unmatched"}</td>
                  <td className="history-ticket">{entry.ticket_id}</td>
                  <td>
                    <span className={`history-provider-tag history-provider-${entry.provider}`}>{entry.provider}</span>
                  </td>
                  <td>
                    {entry.matched ? (
                      <span className={`history-status history-status-${entry.verdict}`}>
                        {entry.verdict?.replace(/_/g, " ").toUpperCase()}
                      </span>
                    ) : (
                      <span className="history-status history-status-unmatched">NO MATCH</span>
                    )}
                  </td>
                  <td>{(entry.total_duration_ms / 1000).toFixed(1)}s</td>
                  <td>{entry.findings_count}</td>
                  <td>{formatDate(entry.created_at)}</td>
                  <td>
                    <Link className="history-view-link" to={`/history/${entry.id}`}>
                      View Report <ExternalLink size={11} aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <div className="history-pagination">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          <ChevronLeft size={14} aria-hidden="true" />
          Previous
        </button>
        <span className="history-pagination-range">Showing {sortedEntries.length ? offset + 1 : 0}–{offset + sortedEntries.length}</span>
        <button type="button" disabled={entries.length < PAGE_SIZE} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Next
          <ChevronRight size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

export default History;
