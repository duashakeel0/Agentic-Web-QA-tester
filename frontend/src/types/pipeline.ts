export type Provider = "claude" | "ollama";
export type ModelChoice = Provider | "both";
export type AgentName = "planner" | "explorer" | "verifier" | "reporter";
// "pass_with_issues" - the run reached the correct final state, but one or
// more real actions failed/needed a retry along the way. Distinct from
// "fail" (final state was never reached) on purpose - not every hiccup is
// a broken workflow.
export type Verdict = "pass" | "pass_with_issues" | "fail";

export interface TestPlan {
  ticket_id: string;
  ticket_title: string | null;
  matched: boolean;
  reason: string | null;
  domain: string | null;
  workflow: string | null;
  steps: string[];
  expected_outcome: { url_contains?: string | null; text_contains?: string | null } | null;
}

export interface ActionLogEntry {
  step: string;
  action: string;
  selector: string | null;
  value: string | null;
  reasoning: string | null;
  success: boolean;
  error: string | null;
  is_broken_input_attempt: boolean;
  screenshot_path: string | null;
}

export interface ExplorationResult {
  ticket_id: string;
  domain: string;
  workflow: string;
  completed: boolean;
  actions: ActionLogEntry[];
  final_url: string | null;
  final_page_text: string | null;
  error: string | null;
}

export interface VerifierResult {
  ticket_id: string;
  domain: string;
  workflow: string;
  verdict: Verdict;
  warning_count: number;
  assertion_checked: Record<string, unknown>;
  initial_check_passed: boolean;
  retried: boolean;
  retry_passed: boolean | null;
  retry_error: string | null;
  explanation: string | null;
  explanation_status: "ok" | "inconclusive" | "skipped";
  screenshot_path: string | null;
}

export interface Finding {
  ticket_id: string;
  domain: string;
  workflow: string;
  severity: "high" | "medium" | "low";
  summary: string;
  error_message: string | null;
  reproduction_steps: string[];
  screenshot_path: string | null;
  explanation: string | null;
}

export interface Report {
  ticket_id: string;
  findings: Finding[];
  post_summary_status: "pending" | "posted" | "failed";
  post_summary_error: string | null;
}

export interface StepTiming {
  agent: AgentName;
  provider: Provider;
  model: string;
  started_at: number;
  finished_at: number;
  duration_ms: number;
}

export interface RunMetrics {
  steps_planned: number;
  steps_covered: number;
  coverage_ratio: number;
  missed_steps: string[];
  actions_attempted: number;
  actions_succeeded: number;
  accuracy_ratio: number;
  llm_call_count: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface PipelineResult {
  ticket_id: string;
  provider: Provider;
  plan: TestPlan;
  exploration: ExplorationResult | null;
  verification: VerifierResult | null;
  report: Report | null;
  timings: StepTiming[];
  metrics: RunMetrics | null;
  started_at: number;
  finished_at: number;
  total_duration_ms: number;
}

export interface ComparisonReport {
  ticket_id: string;
  faster_provider: Provider | null;
  time_difference_ms: number;
  verdict_agreement: boolean;
  claude_verdict: Verdict | null;
  ollama_verdict: Verdict | null;
  claude_total_duration_ms: number;
  ollama_total_duration_ms: number;
  claude_findings_count: number;
  ollama_findings_count: number;
  claude_metrics: RunMetrics | null;
  ollama_metrics: RunMetrics | null;
  missed_only_by_claude: string[];
  missed_only_by_ollama: string[];
  cost_difference_usd: number;
  cheaper_provider: Provider | null;
  more_accurate_provider: Provider | null;
  better_coverage_provider: Provider | null;
  summary: string;
}

export interface TargetBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Viewport {
  width: number;
  height: number;
}

export type PipelineEvent =
  | { type: "stage_start"; provider: Provider; agent: AgentName }
  | { type: "stage_end"; provider: Provider; agent: AgentName; duration_ms: number; message: string }
  | { type: "stage_error"; provider: Provider; agent: AgentName; message: string }
  | {
      type: "action";
      provider: Provider;
      agent: AgentName;
      step: string;
      action: string;
      selector: string | null;
      value: string | null;
      success: boolean;
      error: string | null;
      screenshot_url: string | null;
      target_box: TargetBox | null;
      viewport: Viewport | null;
    }
  | { type: "pipeline_done"; provider: Provider; history_id: number; result: PipelineResult }
  | { type: "comparison_done"; comparison_group: string; comparison: ComparisonReport }
  | { type: "error"; provider?: Provider; message: string };
