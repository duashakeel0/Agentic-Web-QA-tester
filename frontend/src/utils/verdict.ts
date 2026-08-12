/** Turns a raw verdict value into what's actually shown on screen. "fail"
 * displays as "ISSUE FOUND" rather than "FAIL" - by the time a run
 * reaches this verdict, the agent has already run the workflow
 * correctly and found a real defect on the site under test (every
 * report/verifier fix this project has gone through exists specifically
 * to make sure "fail" only ever means that, not a tool-side hiccup) - so
 * the label should read as a finding about the site, not as the AI
 * having failed to do its job. Every other verdict displays as its own
 * plain, underscore-free uppercase text, same as before.
 */
export function verdictLabel(verdict: string | null | undefined): string {
  if (!verdict) return "n/a";
  if (verdict === "fail") return "ISSUE FOUND";
  return verdict.replace(/_/g, " ").toUpperCase();
}
