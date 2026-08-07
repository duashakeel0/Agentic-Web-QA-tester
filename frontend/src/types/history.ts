import type { ComparisonReport, PipelineResult, Provider, Verdict } from "./pipeline";

export interface HistoryEntry {
  id: number;
  ticket_id: string;
  domain: string | null;
  workflow: string | null;
  provider: Provider;
  matched: boolean;
  verdict: Verdict | null;
  findings_count: number;
  total_duration_ms: number;
  estimated_cost_usd: number;
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
  total_cost_usd: number;
  by_provider: Record<string, number>;
}

export interface MissedStepCount {
  step: string;
  count: number;
}

export interface ProviderStats {
  provider: Provider;
  run_count: number;
  pass_count: number;
  fail_count: number;
  avg_duration_ms: number;
  avg_coverage_ratio: number;
  avg_accuracy_ratio: number;
  avg_cost_usd: number;
  total_cost_usd: number;
  common_missed_steps: MissedStepCount[];
}

export interface DailyStat {
  date: string;
  total: number;
  passed: number;
  failed: number;
  total_cost_usd: number;
  avg_duration_ms: number;
}

export interface SiteStats {
  domain: string;
  run_count: number;
  passed: number;
  failed: number;
  last_tested_at: number;
}
