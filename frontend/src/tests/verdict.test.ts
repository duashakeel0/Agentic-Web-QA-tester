import { describe, expect, it } from "vitest";
import { verdictLabel } from "../utils/verdict";

describe("verdictLabel", () => {
  it("reads a fail verdict as ISSUE FOUND, not FAIL", () => {
    // "FAIL" reads as if the AI agent itself failed to do its job - by
    // this point it ran the workflow correctly and found a real defect
    // on the site under test, so the label reflects that instead.
    expect(verdictLabel("fail")).toBe("ISSUE FOUND");
  });

  it("leaves every other verdict as plain uppercase text", () => {
    expect(verdictLabel("pass")).toBe("PASS");
    expect(verdictLabel("pass_with_issues")).toBe("PASS WITH ISSUES");
  });

  it("falls back to n/a for a missing verdict", () => {
    expect(verdictLabel(null)).toBe("n/a");
    expect(verdictLabel(undefined)).toBe("n/a");
  });
});
