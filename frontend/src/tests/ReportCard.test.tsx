import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import ReportCard from "../components/ReportCard";
import type { PipelineResult } from "../types/pipeline";

function basePlan(overrides: Partial<PipelineResult["plan"]> = {}): PipelineResult["plan"] {
  return {
    ticket_id: "T1", ticket_title: "Verify login works", matched: true,
    reason: null, domain: "practice_software_testing", workflow: "login", steps: ["Log in"],
    expected_outcome: { url_contains: "/inventory.html" },
    ...overrides,
  };
}

function passingResult(): PipelineResult {
  return {
    ticket_id: "T1", provider: "claude", plan: basePlan(),
    exploration: {
      ticket_id: "T1", domain: "practice_software_testing", workflow: "login", completed: true,
      actions: [], final_url: "https://x/inventory.html", final_page_text: "Products", error: null,
    },
    verification: {
      ticket_id: "T1", domain: "practice_software_testing", workflow: "login", verdict: "pass", warning_count: 0,
      assertion_checked: {}, initial_check_passed: true, retried: false, retry_passed: null,
      retry_error: null, explanation: null, explanation_status: "ok", screenshot_path: null,
    },
    report: { ticket_id: "T1", findings: [], post_summary_status: "posted", post_summary_error: null },
    timings: [], metrics: null, started_at: 0, finished_at: 3.5, total_duration_ms: 3500,
  };
}

function failingResult(): PipelineResult {
  const result = passingResult();
  return {
    ...result,
    verification: { ...result.verification!, verdict: "fail", initial_check_passed: false },
    report: {
      ticket_id: "T1",
      findings: [
        {
          ticket_id: "T1", domain: "practice_software_testing", workflow: "login", severity: "high",
          summary: "Login button does not respond.", error_message: "Timed out waiting for '#login-button'",
          reproduction_steps: ["click on #login-button"], screenshot_path: null, explanation: null,
        },
      ],
      post_summary_status: "posted", post_summary_error: null,
    },
  };
}

describe("ReportCard", () => {
  it("shows a NO MATCH badge when the plan didn't match a domain", () => {
    const result: PipelineResult = {
      ...passingResult(),
      plan: basePlan({ matched: false, domain: null, workflow: null, reason: "No registered domain matches." }),
    };

    render(<ReportCard result={result} />);

    expect(screen.getByText("NO MATCH")).toBeInTheDocument();
    expect(screen.getByText("No registered domain matches.")).toBeInTheDocument();
  });

  it("shows a PASS badge and no findings for a passing run", () => {
    render(<ReportCard result={passingResult()} />);

    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText(/expected outcome was verified/)).toBeInTheDocument();
  });

  it("shows an ISSUE FOUND badge (not FAIL) with failure reason and error message", () => {
    // "FAIL" reads as if the AI agent itself failed to do its job - by
    // this point it ran the workflow correctly and found a real defect
    // on the site under test, so the badge says so instead.
    render(<ReportCard result={failingResult()} />);

    expect(screen.getByText("ISSUE FOUND")).toBeInTheDocument();
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    expect(screen.getByText(/Login button does not respond/)).toBeInTheDocument();
    expect(screen.getByText(/Timed out waiting for '#login-button'/)).toBeInTheDocument();
  });

  it("shows a PASS WITH ISSUES badge, not FAIL, when the run recovered from errors", () => {
    const result = passingResult();
    result.verification = { ...result.verification!, verdict: "pass_with_issues", warning_count: 1 };
    result.report = {
      ticket_id: "T1",
      findings: [
        {
          ticket_id: "T1", domain: "practice_software_testing", workflow: "login", severity: "low",
          summary: "Workflow completed and passed, but 1 action(s) failed or needed a retry along the way.",
          error_message: null, reproduction_steps: [], screenshot_path: null, explanation: null,
        },
      ],
      post_summary_status: "posted", post_summary_error: null,
    };

    render(<ReportCard result={result} />);

    expect(screen.getByText("PASS WITH ISSUES")).toBeInTheDocument();
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    expect(screen.getByText(/1 action\(s\) failed or needed a retry/)).toBeInTheDocument();
  });

  it("renders a Test Case Execution Details table derived from the action log", () => {
    const result = passingResult();
    result.plan = basePlan({ steps: ["Navigate to the homepage", "Log in with valid credentials"] });
    result.exploration = {
      ...result.exploration!,
      completed: true,
      actions: [
        { step: "Log in with valid credentials", action: "fill", selector: "#user", value: "bob", reasoning: null, success: true, error: null, is_broken_input_attempt: false, screenshot_path: null },
      ],
    };

    render(<ReportCard result={result} />);

    // Step 1 had no actions but the run completed - reads as skipped
    // (already satisfied), not as a failure.
    expect(screen.getByText("Navigate to the homepage")).toBeInTheDocument();
    expect(screen.getByText("Log in with valid credentials")).toBeInTheDocument();
    expect(screen.getByText("SKIPPED")).toBeInTheDocument();
    expect(screen.getAllByText("PASS").length).toBeGreaterThan(0); // badge + step status
  });

  it("shows a FAIL step status distinct from a SKIPPED one for the same run", () => {
    const result = failingResult();
    result.plan = basePlan({ steps: ["Log in"] });
    result.exploration = {
      ...result.exploration!,
      completed: false,
      actions: [
        { step: "Log in", action: "click", selector: "#login-button", value: null, reasoning: null, success: false, error: "Timed out", is_broken_input_attempt: false, screenshot_path: null },
      ],
    };

    render(<ReportCard result={result} />);

    // The header badge reads "ISSUE FOUND" (a finding about the site),
    // while the step-table status cell for the specific action that
    // failed still reads "FAIL" (an execution-level outcome) - the two
    // are deliberately different labels for different things.
    expect(screen.getByText("ISSUE FOUND")).toBeInTheDocument();
    expect(screen.getAllByText("FAIL").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Timed out")).toBeInTheDocument();
  });

  it("shows FAIL on the last real step when every action succeeded but the workflow's overall verdict is fail", () => {
    // Reproduces a real practice_software_testing login report: every
    // action (fill email, fill password, click login) genuinely
    // succeeded with no error, yet the site never actually authenticated
    // - the FAIL badge next to an all-PASS step table read as a
    // contradiction. Only the last real action (the one the final
    // assertion depends on) should read FAIL; the earlier steps that
    // genuinely achieved their own local goal stay PASS.
    const result = failingResult();
    result.plan = basePlan({ steps: ["Enter the email", "Enter the password", "Click the Login button"] });
    result.exploration = {
      ...result.exploration!,
      completed: true,
      actions: [
        { step: "Enter the email", action: "fill", selector: "#email", value: "customer@example.com", reasoning: null, success: true, error: null, is_broken_input_attempt: false, screenshot_path: null },
        { step: "Enter the password", action: "fill", selector: "#password", value: "welcome01", reasoning: null, success: true, error: null, is_broken_input_attempt: false, screenshot_path: null },
        { step: "Click the Login button", action: "click", selector: "input[type='submit']", value: null, reasoning: null, success: true, error: null, is_broken_input_attempt: false, screenshot_path: null },
      ],
    };

    render(<ReportCard result={result} />);

    const emailRow = screen.getByText("Enter the email").closest("tr")!;
    const passwordRow = screen.getByText("Enter the password").closest("tr")!;
    const loginRow = screen.getByText("Click the Login button").closest("tr")!;
    expect(within(emailRow).getByText("PASS")).toBeInTheDocument();
    expect(within(passwordRow).getByText("PASS")).toBeInTheDocument();
    expect(within(loginRow).getByText("FAIL")).toBeInTheDocument();
    expect(within(loginRow).getByText(/did not achieve the expected outcome/)).toBeInTheDocument();
  });

  it("shows PASS for a step that succeeded before a later, unrelated hiccup", () => {
    // Reproduces a real ParaBank report: the submit click actually
    // succeeded, but the loop queried the model again before the
    // confirmation had rendered, and that second, redundant decision hit
    // an unrelated LLM parsing error - logged as the step's *last* action
    // even though the step's real goal was already achieved by the first
    // one. The step genuinely passed and must not read FAIL just because
    // its last logged attempt was noise.
    const result = passingResult();
    result.verification = { ...result.verification!, verdict: "pass_with_issues", warning_count: 1 };
    result.plan = basePlan({ steps: ["Submit the transfer"] });
    result.exploration = {
      ...result.exploration!,
      completed: true,
      actions: [
        { step: "Submit the transfer", action: "click", selector: "input[type='submit']", value: null, reasoning: null, success: true, error: null, is_broken_input_attempt: false, screenshot_path: null },
        { step: "Submit the transfer", action: "unknown", selector: null, value: null, reasoning: null, success: false, error: "claude returned an unparseable response", is_broken_input_attempt: false, screenshot_path: null },
      ],
    };

    render(<ReportCard result={result} />);

    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.queryByText("FAIL")).not.toBeInTheDocument();
    expect(screen.getByText("Completed successfully in 2 action(s).")).toBeInTheDocument();
  });

  it("renders a Test Execution Summary donut once metrics are available", () => {
    const result = passingResult();
    result.metrics = {
      steps_planned: 4, steps_covered: 4, coverage_ratio: 1, missed_steps: [],
      actions_attempted: 5, actions_succeeded: 4, accuracy_ratio: 0.8,
      llm_call_count: 5, input_tokens: 100, output_tokens: 50, estimated_cost_usd: 0.01,
    };

    render(<ReportCard result={result} />);

    expect(screen.getByText("Test Execution Summary")).toBeInTheDocument();
    expect(screen.getByText("Passed (4)")).toBeInTheDocument();
    expect(screen.getByText("Failed (1)")).toBeInTheDocument();
  });

  it("skips the Test Execution Summary section when there are no metrics", () => {
    render(<ReportCard result={passingResult()} />);

    expect(screen.queryByText("Test Execution Summary")).not.toBeInTheDocument();
  });

  it("hides agent outputs behind a toggle until clicked", async () => {
    const user = userEvent.setup();
    const result = failingResult();
    result.exploration!.actions = [
      { step: "Log in", action: "click", selector: "#login-button", value: null, reasoning: null, success: false, error: "boom", is_broken_input_attempt: false, screenshot_path: null },
    ];

    render(<ReportCard result={result} />);

    expect(document.querySelector(".report-actions-list")).not.toBeInTheDocument();

    await user.click(screen.getByText(/Show action log/));

    expect(document.querySelector(".report-actions-list")).toBeInTheDocument();
    expect(screen.getByText(/Hide action log/)).toBeInTheDocument();
  });
});
