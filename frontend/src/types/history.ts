import type { ComparisonReport, PipelineResult, Provider } from "./pipeline";

export interface HistoryEntry {
  id: number;
  ticket_id: string;
  domain: string | null;
  workflow: string | null;
  provider: Provider;
  matched: boolean;
  verdict: "pass" | "fail" | null;
  findings_count: number;
  total_duration_ms: number;
  started_at: number;
  finished_at: number;
  comparison_group: string | null;
  created_at: number;
}

export interface HistoryDetail extends HistoryEntry {
  result: PipelineResult;
}

export interface ComparisonHistoryEntry {
  comparison_group: string;
  ticket_id: string;
  comparison: ComparisonReport;
  created_at: number;
}

export interface HistoryStats {
  total_runs: number;
  passed: number;
  failed: number;
  unmatched: number;
  avg_duration_ms: number;
  by_provider: Record<string, number>;
}
