import { render, screen } from "@testing-library/react";
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

  it("shows a FAIL badge with failure reason and error message", () => {
    render(<ReportCard result={failingResult()} />);

    expect(screen.getByText("FAIL")).toBeInTheDocument();
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
