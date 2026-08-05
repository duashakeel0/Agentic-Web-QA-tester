import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AskAboutTest from "../components/AskAboutTest";
import ComparisonSummary from "../components/ComparisonSummary";
import ReportCard from "../components/ReportCard";
import { apiGet, ApiError } from "../services/api";
import { useAuth } from "../contexts/AuthContext";
import type { ComparisonHistoryEntry, HistoryDetail } from "../types/history";
import type { PipelineResult } from "../types/pipeline";
import "./HistoryReport.css";

function HistoryReport() {
  const { id } = useParams<{ id: string }>();
  const { logout } = useAuth();
  const [entry, setEntry] = useState<HistoryDetail | null>(null);
  const [siblingResult, setSiblingResult] = useState<PipelineResult | null>(null);
  const [comparison, setComparison] = useState<ComparisonHistoryEntry | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    apiGet<HistoryDetail>(`/api/history/${id}`)
      .then(async (data) => {
        if (cancelled) return;
        setEntry(data);

        if (data.comparison_group) {
          const [comparisonData, siblingRuns] = await Promise.all([
            apiGet<ComparisonHistoryEntry>(`/api/history/comparisons/${data.comparison_group}`).catch(() => null),
            apiGet<HistoryDetail[]>(`/api/history?search=${encodeURIComponent(data.ticket_id)}&limit=50`).catch(() => []),
          ]);
          if (cancelled) return;
          if (comparisonData) setComparison(comparisonData);
          const sibling = siblingRuns.find((r) => r.comparison_group === data.comparison_group && r.id !== data.id);
          if (sibling) {
            const siblingDetail = await apiGet<HistoryDetail>(`/api/history/${sibling.id}`).catch(() => null);
            if (!cancelled && siblingDetail) setSiblingResult(siblingDetail.result);
          }
        }
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          logout();
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load this report.");
      });

    return () => {
      cancelled = true;
    };
  }, [id, logout]);

  return (
    <div className="history-report-page">
      <Link to="/history" className="history-report-back">
        ← Back to History
      </Link>
      <h1 className="history-report-title">Report</h1>

      {error && <p className="history-report-error">{error}</p>}
      {!entry && !error && <p className="history-report-loading">Loading…</p>}

      {entry && (
        <>
          <div className="history-report-grid">
            <ReportCard result={entry.result} />
            {siblingResult && <ReportCard result={siblingResult} />}
          </div>
          <div className="history-report-ask">
            <AskAboutTest runId={entry.id} />
          </div>
        </>
      )}

      {comparison && (
        <div className="history-report-comparison">
          <ComparisonSummary comparison={comparison.comparison} />
        </div>
      )}
    </div>
  );
}

export default HistoryReport;
