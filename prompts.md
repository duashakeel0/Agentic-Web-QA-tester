# Prompts Log

Running log of significant AI prompts used to build this project, per the internship's AI-coding-discipline requirement. Updated as work happens, not compiled after the fact.

---

## Day 1 — Repo Scaffold, Environment & Documentation Gate

**Prompt:** Scaffold a new full-stack project — React + TypeScript frontend (Vite) and Python FastAPI backend — for an AI agent that tests websites. Set up a mock end-to-end stub (backend returns a fake test-run result, frontend fetches and displays it) so the pipeline is proven before any real agent logic exists.

**What was generated:**
- `frontend/` — Vite + React + TS scaffold (`npm create vite@latest -- --template react-ts`), default template assets removed, `App.tsx` rewritten to fetch and display a mock test-run result from the backend
- `backend/app/main.py` — a FastAPI app with a `/api/health` check and a `/api/mock-run` endpoint returning a hardcoded fake result
- `README.md` — architecture diagram (Mermaid), tech stack, model-selection rationale, run instructions
- This file

**What was checked/modified before accepting:**
- Ran `npm run lint` (oxlint) on the frontend — clean pass
- Ran `tsc -b && npm run build` — compiles and builds cleanly
- Started both servers and used Playwright to actually load the page in a real browser and confirm the mock data renders correctly — not just assumed from the dev server logs
- Removed the default Vite template's demo content (counter button, logo images, "next steps" links) since none of it applies to this project

---

## Day 1 (follow-up) — Frontend Folder Restructure

**Context:** PR review feedback recommended a clearer folder structure for the frontend before the project grows, since retrofitting one later is more painful than setting it up now.

**Prompt:** Restructure the frontend `src/` into `assets/`, `shared-components/`, `data/services/`, `hooks/`, `layouts/`, `pages/`, `routes/`, `tests/`, `types/`, `utils/`. Move the existing mock-run logic out of `App.tsx` into the appropriate folders (a type, a service function, a hook, and a page component), leaving `App.tsx` as a thin root shell.

**What was generated:**
- `types/testRun.ts` — the `TestRunResult` interface, moved out of the page component
- `data/services/testRunService.ts` — the `fetchMockRun` API call
- `hooks/useMockRun.ts` — wraps the fetch + loading/error state
- `pages/Dashboard.tsx` (+ `Dashboard.css`) — the actual page content, moved out of `App.tsx`
- `App.tsx` reduced to a thin shell rendering `Dashboard`
- `.gitkeep` placeholders in the folders with nothing in them yet (`shared-components`, `layouts`, `routes`, `tests`, `utils`)
- README updated with the folder structure and why some folders are intentionally still empty

**What was checked/modified before accepting:**
- Ran `npm run lint` and `tsc -b && npm run build` again after the move — clean
- Re-ran the full end-to-end browser check with Playwright to make sure the restructure didn't silently break anything — it initially appeared to fail, but the cause was a stale test running on the wrong port (5174 instead of the CORS-allowed 5173), not an actual bug in the restructured code. Re-verified on the correct port and confirmed the page still renders the mock result correctly.

---

## Day 2 — Browser Driver & Live Dashboard Connection

**Prompt:** Replace the Day 1 mock data flow with a real Playwright browser driver on the backend, connected to the dashboard over a WebSocket instead of a one-off fetch, so status updates stream to the frontend live as a real browser action happens.

**What was generated:**
- `backend/app/browser.py` — a `BrowserSession` class wrapping Playwright's async API (start a browser, navigate, read the page title, close)
- `backend/app/main.py` — a new `/ws/run` WebSocket endpoint: accepts a URL from the client, launches a browser, and streams `status` messages as each step happens, then a final `done` (or `error`) message
- `frontend/src/types/liveRun.ts` — types for the WebSocket message shapes
- `frontend/src/data/services/liveRunService.ts` — builds the WebSocket URL
- `frontend/src/hooks/useLiveRun.ts` — opens the WebSocket, sends the URL, and tracks the incoming log/result/error/running state
- `pages/Dashboard.tsx` — replaced the Day 1 mock display with a URL input, "Run test" button, and a live log view
- Removed the now-unused Day 1 mock files (`useMockRun.ts`, `testRunService.ts`, `types/testRun.ts`) since the live driver replaces that flow
- `requirements.txt` — added `playwright`; removed `uvloop` (an optional performance extra that doesn't build on Windows and wasn't needed)
- README updated to describe the WebSocket flow and add the `playwright install chromium` setup step

**What was checked/modified before accepting:**
- Ran `npm run lint` and `tsc -b && npm run build` on the frontend — clean
- Verified the backend imports and starts correctly with the new Playwright dependency
- Ran the full flow live in a real browser with Playwright: opened the dashboard, entered a URL, clicked "Run test," and confirmed the live log messages ("Launching browser...", "Navigating to...") and the final page-title result rendered correctly end to end over the actual WebSocket connection — not assumed from code alone

---

## Day 3 — Trello MCP Server (get_ticket & post_summary)

**Prompt:** Build a real MCP server around Trello instead of an ad hoc API call — two narrowly-scoped tools, `get_ticket(ticket_id)` and `post_summary(ticket_id, summary)`, following the MCP Python SDK's resource/tool model.

**What was generated:**
- `backend/app/mcp_server/trello_client.py` — a `TrelloClient` wrapping the Trello REST API directly (nothing else in the project talks to Trello). Reads `TRELLO_API_KEY`/`TRELLO_TOKEN` from the environment, raises a specific `TrelloError` for a missing card, a bad key/token, or missing credentials entirely — never a generic failure
- `backend/app/mcp_server/server.py` — the actual MCP server (FastMCP), exposing `get_ticket` and `post_summary` as tools, each catching `TrelloError` and returning it as a structured `{"error": ...}` result instead of crashing
- `backend/.env.example` — documents the two required Trello environment variables
- `requirements.txt` — added `mcp[cli]` and `httpx`

**What was checked/modified before accepting:**
- Confirmed the server module imports cleanly and both tools register correctly
- Called `get_ticket` directly with no credentials set, to confirm the missing-credentials path returns a clear structured error instead of an unhandled exception
- **Not yet completed:** the acceptance criteria requires connecting to a real Trello test board — not mock data — and using MCP Inspector to manually verify both tools against it. That needs a real Trello API key, token, and test board/card, which aren't available in this environment. The server is structurally complete and ready to wire up the moment those credentials exist; the real-board verification and Inspector walkthrough are still outstanding.

---

## Day 3 (follow-up) — Real-board verification, plus two real bugs found and fixed

**Context:** Once real Trello credentials existed, verification moved to a local machine (this sandbox's network policy blocks `api.trello.com` outright, confirmed via the proxy diagnostics — not something to work around).

**What was found and fixed while verifying live:**
- `requirements.txt` on this branch never actually had `mcp`/`httpx` added — they were only installed into the sandbox's own venv earlier and never committed, so `pip install -r requirements.txt` silently did nothing for those two packages. Fixed and verified in a brand-new virtualenv.
- `mcp dev app/mcp_server/server.py` failed with `ModuleNotFoundError: No module named 'app'` — the MCP CLI loads the server file directly by path rather than as a package-aware import, so `backend/` was never on `sys.path`. Fixed by explicitly inserting it in `server.py`, verified by simulating the same file-path loading mechanism from an unrelated directory.
- **Real bug caught during live testing:** calling `get_ticket` with an invalid ticket ID returned Trello's `400 Bad Request`, which the code's fallback `raise_for_status()` path didn't handle — it crashed instead of returning the structured `{"error": ...}` response the ticket requires. Worse, the raw exception message included the full request URL, which carries the API key and token as query parameters, so the crash also displayed partial credentials in the Inspector UI. Fixed by replacing `raise_for_status()` with explicit status-code handling that never includes the request URL in any error message, and added an explicit 400 case. Verified with a mocked 400 response that the resulting error message contains no `key=`/`token=` substring.

**What was checked/modified before accepting:**
- Verified live against a real Trello board via MCP Inspector: `get_ticket` returns the correct title, description, and real checklist items (with their checked state); `post_summary` posts a real, confirmed comment (verified by the returned `comment_id` and visually on the card)
- Verified the error path live: an invalid ticket ID now returns a clean structured error with no crash and no leaked credentials, instead of the raw exception seen before the fix

---

## Day 4 — Planner Agent

**Prompt:** Build the Planner agent — reads a ticket via `get_ticket`, matches it to a registered domain and workflow using Claude (judgment, not string matching), and produces a structured Pydantic-validated plan. Never lets an unmatched ticket proceed to planning.

**What was generated:**
- `backend/app/domains/schema.py` + `manifest.py` — the domain knowledge schema (Domain/Workflow/ExpectedOutcome) and a loader that reads every `data/*.yaml` file into validated objects. This is technically Day 5's scope, but the Planner can't do anything without it, so it was built here as a dependency rather than stubbed.
- `backend/app/domains/data/*.yaml` — the 3 registered domains per the mentor's scope revision (2-3 domains, not 6, one self-built + established practice sites): `sauce_demo` (saucedemo.com), `the_internet` (the-internet.herokuapp.com), and `campushub` (self-built, base_url is a placeholder pending the actual local address). Each has 3 carefully-written workflows with real expected outcomes.
- `backend/app/agents/planner.py` — `PlannerAgent`: calls `get_ticket`, sends the ticket + full domain manifest to Claude asking it to match a domain/workflow, and **only ever trusts a match that actually exists in the manifest** — if Claude names something outside the registered list, that's treated as unmatched rather than followed.
- `backend/app/agents/schema.py` — the `TestPlan` Pydantic model the Explorer will consume next.
- `backend/app/agents/run_planner.py` — a small CLI (`python -m app.agents.run_planner <ticket_id>`) to manually run the Planner against a real ticket and review its output, since that's what this ticket's acceptance criteria requires.
- `requirements.txt` — added `anthropic` and `PyYAML`.

**What was checked/modified before accepting:**
- Confirmed all 3 domain YAML files load correctly into validated `Domain` objects
- Confirmed `PlannerAgent()` raises a clear `PlannerError` when `ANTHROPIC_API_KEY` isn't set, instead of failing unhelpfully later
- Verified the full matching logic with a mocked Claude response across three cases: (1) a clean match produces the correct structured plan with the right steps and expected outcome, (2) an explicit "not matched" response from the model is passed through correctly, (3) **critically** - a model response naming a domain/workflow that doesn't actually exist in the manifest is correctly treated as unmatched rather than trusted, since that would otherwise let a hallucinated match slip through
- Verified `requirements.txt` installs cleanly in a brand-new virtualenv
- Verified live against 4 real Trello tickets once a real `ANTHROPIC_API_KEY` was available: 3 tickets spanning 2 domains (`sauce_demo`, `the_internet`) all matched correctly with the right workflow and steps; 1 deliberately unregistered-domain ticket (Amazon) correctly returned `matched: false` with a clear reason instead of a guessed or hallucinated match

**Note on Day 5 overlap:** building the domain knowledge store here (to unblock the Planner) completes most of Day 5's acceptance criteria as a side effect - the schema, the manifest loader, and 2 of the 3 domains (`sauce_demo`, `the_internet`) are fully working and proven by the live test above. Still open for Day 5 specifically: `campushub`'s `base_url` is a placeholder pending the real local address, and the "add a 4th domain with zero code changes" claim hasn't been demonstrated yet.

---

## Day 5 — Domain Knowledge Store: Real CampusHub Data & Extensibility Proof

**Prompt:** Close out the two things Day 4 left open for this ticket: replace CampusHub's placeholder route/success-text data with the real values from the actual frontend, and demonstrate that a new domain can be registered with zero code changes.

**What was generated/changed:**
- `backend/app/domains/data/campushub.yaml` — replaced the guessed routes and success text with the real ones from CampusHub's own source: `/login` (form submit shows a "Welcome back!" toast and redirects to `/`, the dashboard, which renders "Welcome to CampusHub"), `/attendance` (submitting the form shows an "Attendance marked successfully!" toast, and the same page lists an "Attendance Records" table). `base_url` corrected to the frontend's actual local dev address rather than the backend API port.

**What was checked/modified before accepting:**
- Re-confirmed all 3 domain YAML files (`campushub`, `sauce_demo`, `the_internet`) still load into validated `Domain`/`Workflow` objects with the corrected data
- Demonstrated the "zero code changes" extensibility claim directly: added a temporary 4th domain YAML file with no matching code changes, confirmed via `load_domains()` that it was picked up automatically, then removed it and confirmed `git status` showed no trace left behind
- Day 5's acceptance criteria is now fully closed: schema, manifest loader, and all 3 real registered domains (one self-built, two established practice sites) working and verified

---

## Day 6 — Explorer Agent

**Prompt:** Build the Explorer - the only agent that touches the browser. It takes the Planner's plan and drives Playwright through the stored workflow's steps, deciding each concrete browser action from the current page state (via Llama 3.1 running locally through Ollama) instead of following a fixed script, so a stored workflow keeps working even if a page's layout shifts slightly.

**What was generated:**
- `backend/app/agents/ollama_client.py` — a thin wrapper around Ollama's local REST API (`/api/generate`, `format: "json"`), raising a specific `OllamaError` for an unreachable server, a non-200 response, or a response that isn't parseable JSON
- `backend/app/agents/explorer.py` — `ExplorerAgent`: for each step in the plan, takes a snapshot of the current page's interactive elements, asks the local model to decide the single next action (fill/click/select/press/navigate/done), executes it via Playwright, and logs the action plus the model's stated reasoning. Also runs one deliberate broken-input attempt (empty/invalid value) on the first genuinely interactive step of each workflow, tagged separately from the real attempt so the Reporter can tell them apart. A per-step action budget and a same-action repeat counter stop it from looping forever if the model gets stuck suggesting the same click over and over.
- `backend/app/agents/schema.py` — added `ActionLogEntry` and `ExplorationResult`, the structured, validated shape the Reporter will read next.
- `backend/app/agents/run_explorer.py` — a CLI (`python -m app.agents.run_explorer <ticket_id>`) that runs the Planner and Explorer back to back against a real ticket and prints the full exploration log.
- `backend/app/browser.py` — added a `page` property so the Explorer can drive Playwright's fill/click/select/evaluate calls directly instead of only the single `goto()` method Day 2 needed.
- `backend/.env.example` — documents `OLLAMA_HOST`/`OLLAMA_MODEL`.
- README — added the Explorer's local run instructions (`ollama serve`, pull `llama3.1`, run the CLI).

**What was checked/modified before accepting:**
- Verified all 4 `OllamaClient` error paths against a mocked HTTP layer: unreachable server, non-200 response, malformed JSON in the model's response, and a valid response parsing correctly
- Built a small local static page (a login form with real inputs and a real "empty fields → error, otherwise → welcome message" script) and drove the real Explorer against it end to end with a scripted stand-in for Ollama (so the actual browser/logging/loop-guard code runs for real, without depending on a live Ollama server in this environment): confirmed the happy path completes, exactly one broken-input attempt is logged with the deliberately empty value, and the final page text correctly reflects the real "Welcome" message
- Verified the loop guard: fed the Explorer the same action repeatedly and confirmed it stops with a clear error after a bounded number of repeats instead of looping forever
- Verified an unmatched plan and a plan referencing an unregistered domain are both rejected before the browser is ever launched
- Caught and fixed a bug in my own test setup during this process (not the Explorer itself): a "Navigate to..." step still goes through the same decision loop as any other step (so it can confirm the page already satisfies it), which my first test script didn't account for - once fixed, the real behavior was confirmed correct
- **Not yet completed:** the acceptance criteria requires testing end-to-end against all 3 real registered domains with a real local Llama 3.1 - Ollama isn't available in this environment, so that live run (and any real bugs it turns up) is still outstanding, the same way Day 3's real-Trello-board verification and Day 4's real-Claude verification were.

---

## Day 7 — Verifier Agent and failure handling

**Prompt:** Build the Verifier - it checks the Explorer's result against the workflow's stored, known-correct assertion instead of a subjective read of the page ("loaded with no error" isn't the same as "correct"), retries once before confirming anything to separate a one-off slow render from a real bug, and handles the failure-mode behavior committed to in the proposal (LLM timeouts, browser crashes) explicitly rather than letting them hang or fail silently.

**What was generated:**
- `backend/app/agents/verifier.py` — `VerifierAgent`: checks the Explorer's final URL/page text against the workflow's stored `expected_outcome` (url/text assertions - never a generic pass/fail). A failed check is re-run once on the exact same live page the Explorer ended on (not a fresh, logged-out navigation) after a short wait, which is what actually distinguishes a slow render from a real bug. Also asks Claude for a one-sentence, human-readable explanation of the verdict for the Reporter; that call has its own timeout with one retry at a shorter timeout, and a second failure is marked `inconclusive` explicitly rather than silently folded into a pass or a fail.
- `backend/app/agents/schema.py` — added `VerifierResult`.
- `backend/app/agents/explorer.py` — added a `close_browser` option and a `browser` property so the Verifier can reuse the Explorer's still-open session for its re-check instead of losing login state on a fresh navigation.
- `backend/app/agents/run_verifier.py` — CLI that chains Planner → Explorer → Verifier against a real ticket and prints the final verdict.
- README — added the Verifier's run instructions.

**What was checked/modified before accepting:**
- A full mocked test suite exercising the real `VerifierAgent` code (not reimplemented logic) across: a clean pass needing no retry; a retry correctly filtering a one-off slow render (the same live page returns the right text a moment later); a deliberately broken step staying flagged as a real failure even after the retry; a browser crash mid-recheck producing a clean teardown and a specific error message instead of a hang; an LLM call timing out once and succeeding on the shorter retry; two consecutive LLM timeouts being marked `inconclusive` without ever silently flipping the underlying pass/fail verdict; and an incomplete exploration failing immediately without wasting a retry or an LLM call on it.
- Additionally ran one real end-to-end pass through an actual live browser (not mocked) against a small test page with a deliberately introduced bug - a login button that navigates to the wrong page instead of showing the expected welcome text - and confirmed the Verifier correctly caught and flagged it as a failure after the retry, using the real Explorer→Verifier browser hand-off.
- **Not yet completed:** live verification against all 3 real registered domains still depends on the same local Ollama setup Day 6 is waiting on.

---

## Day 8 — Reporter Agent & Email Notifications

**Prompt:** Build the Reporter - it turns the Verifier's confirmed findings into one severity-ranked report with reproduction steps and a screenshot, writes it back to the originating ticket via `post_summary` with no manual step, and fires an immediate email alert for anything high-severity separately from the full report, since the point of an alert is escalation and not everything belongs in someone's inbox.

**What was generated:**
- `backend/app/agents/reporter.py` — `ReporterAgent`: takes a list of paired Explorer/Verifier outcomes (not just one - a real run, and the future Scheduler's nightly batch, can confirm several findings of different severities at once), classifies each confirmed failure's severity via Claude (defaulting to "high" if that classification call itself fails or times out - a broken classifier should never quietly downgrade a real bug), ranks findings highest-severity first, sends an email alert the moment a finding is confirmed high-severity rather than waiting for the whole report, then writes the combined summary back to the ticket via `post_summary` with one retry on failure - the local report is still returned even if the write-back never succeeds.
- `backend/app/agents/email_sender.py` — a thin `smtplib` wrapper (`EmailSender`) so the Reporter never touches raw SMTP, raising a specific `EmailError` for missing config or a send failure instead of crashing the whole run.
- `backend/app/agents/schema.py` — added `RunResult` (pairs one Explorer + Verifier outcome), `Finding`, and `Report`.
- `backend/app/agents/verifier.py` — the Verifier now captures a screenshot of the live page the moment a failure is confirmed (best-effort - skipped if the browser's already crashed), since the Reporter's findings need one.
- `backend/app/agents/run_reporter.py` — CLI chaining Planner → Explorer → Verifier → Reporter against a real ticket.
- `backend/.env.example` / README — documents the SMTP env vars and the Reporter's run instructions.

**What was checked/modified before accepting:**
- A run with a deliberate mix of severities (high/medium/low) correctly ranks all three findings highest-first and sends exactly one alert email - for the high-severity one only
- The alert email is fired at the moment its finding is confirmed, not batched with the rest of the report - verified by making the (mocked) Trello write-back artificially slow and confirming the email was already sent well before the run finished, comfortably inside the 5-second budget
- `post_summary` retried exactly once on failure (2 total attempts, not more), correctly marked `failed` with the real error attached afterward, and confirmed the local report (all findings, reproduction steps, screenshots) still generates in full even though the write-back never succeeded
- A severity-classification call that fails/times out defaults to "high" rather than silently dropping or downgrading a real finding, and still triggers its alert
- Reproduction steps are built only from the real action sequence, excluding the deliberate broken-input attempts logged by the Explorer, so they actually reproduce the confirmed bug rather than the intentional bad-input detour

---

## Domain Knowledge Refresh — Replacing the shallow practice sites with full-workflow ones

**Context:** Mentor feedback: `sauce_demo`, `the_internet`, and the read-only `amazon` add-on were too shallow - single-form widget tests, not the kind of whole, multi-step workflow (login → find something → do something → confirm) the proposal actually describes. Registered domains needed to change without touching the proposal document itself.

**Prompt:** Replace the 3 shallow registered domains with deeper ones while keeping the self-built `campushub` domain untouched: ParaBank (Parasoft's public demo banking app - login, transfer funds, pay a bill), practicesoftwaretesting.com/Toolshop (login, browse + add to cart, contact form), and automationexercise.com (browse + add to cart, contact form) - all sites built specifically for QA automation practice, matching the proposal's own stated selection criteria (Section 7).

**What was generated:**
- `backend/app/domains/data/parabank.yaml`, `practice_software_testing.yaml`, `automation_exercise.yaml` - new domain files, 2-3 workflows each
- Removed `sauce_demo.yaml`, `the_internet.yaml`, `amazon.yaml`
- Updated every test fixture that referenced the removed domain names (`test_domains_manifest.py`, `test_planner.py`, plus fixture-only mentions across the reporter/verifier/pipeline/history-store/PDF-report/functional test suites and the frontend's `ReportCard.test.tsx`) - left `test_explorer.py`'s Sauce Demo/the-internet references alone since those reproduce specific historical bugs against the sites where they actually happened, not domain declarations

**What was checked/modified before accepting:**
- `load_domains()` loads all 4 new/kept domains correctly with no schema errors
- Full backend suite (147 tests) and frontend suite (14 tests) pass; `tsc`/`oxlint` clean
- **Not yet completed, and worth flagging explicitly:** this sandbox's network egress is locked down to an allowlist that excludes these sites, so routes/success text were sourced from web search (each site's own test-case docs, well-known public test suites against them) rather than by loading the live pages directly - confidence is high for automationexercise.com and ParaBank's page-level flow (both extremely well-documented, stable QA-practice targets), lower for exact wording on practicesoftwaretesting.com's cart/checkout copy. ParaBank also has no fixed public login (unlike Sauce Demo) - its `login`/`transfer_funds`/`pay_bill` workflows have placeholder credentials that need a real registered ParaBank account swapped in before they'll pass. All of this needs a real local run to confirm, the same way Day 6/7's Ollama-dependent live verification did.
- Re-ran the full Day 7 Verifier test suite after adding screenshot capture to confirm nothing regressed

---

## Pass-with-issues verdict

**Context:** A run that reached the correct final state but hit a recoverable error along the way (a field that needed a retry, one action that failed but didn't derail the workflow) was being reported as an outright FAIL - the same category as a run that never got there at all. That conflates "something is genuinely broken" with "it worked, imperfectly," which loses real signal and makes minor hiccups look like blocking bugs.

**Prompt:** Give the Verifier a third verdict - `pass_with_issues` - for exactly the case where the final expected outcome is reached but one or more real (non-broken-input-probe) actions failed on the way there. Wire it through the Reporter (a low-severity informational finding, never an email alert), the Trello comment, the PDF report, and the dashboard (a third amber badge next to PASS/FAIL everywhere a verdict is shown), and count it as a pass for aggregate stats (pass rate, daily chart) since the workflow genuinely completed correctly.

**What was generated:**
- `backend/app/agents/schema.py` - `VerifierResult.warning_count`, `verdict` now `"pass" | "pass_with_issues" | "fail"`
- `backend/app/agents/verifier.py` - counts real action failures (excluding deliberate broken-input probes); if the final assertion holds despite them, verdict is `pass_with_issues`, never `fail`
- `backend/app/agents/reporter.py` - generates a low-severity finding for `pass_with_issues` without an LLM classification call or an alert email; fixed `_render_summary`'s pass/fail split, which previously miscounted anything not exactly "pass" as failed
- `backend/app/history/store.py`, `backend/app/pdf_report.py` - `pass_with_issues` counts toward the aggregate pass rate; PDF verdict color gets a third (amber) option
- Frontend: `types/pipeline.ts`/`types/history.ts` get a shared `Verdict` type; `ReportCard`, `Dashboard`, `History`, `ComparisonSummary` all render a third "PASS WITH ISSUES" badge instead of forcing a binary pass/fail

**What was checked/modified before accepting:**
- New Verifier unit tests: a run with one failed action but a correct final state gets `pass_with_issues`; a deliberate broken-input probe failing does NOT trigger it (still a clean `pass`)
- New Reporter unit tests: `pass_with_issues` produces exactly one low-severity finding with no LLM call and no alert email; `_render_summary`'s pass/fail counts no longer misclassify it
- New ReportCard test: a `pass_with_issues` result renders the amber badge, never the FAIL badge
- Full backend suite (152 tests) and frontend suite (15 tests) pass; `tsc`/`oxlint` clean

---

## Domain knowledge model clarification - goal vs. steps vs. ticket

**Context:** Mid-build, tried collapsing each domain's workflow from a detailed step list down to one autonomous goal sentence, on the read that "the agent should know the steps itself, not be told." Corrected: the proposal's domain knowledge model already has the agent finding the real element for each step itself (Section 5) - what it doesn't do is invent the step *sequence* from nothing. The domain YAML stays the detailed, known-correct flow a human tester would follow (per Section 7, verbatim); a ticket is what tells the Planner *which* registered workflow to run, not a restatement of its steps.

**What was generated:** Reverted the single-goal collapse - `parabank.yaml`, `practice_software_testing.yaml`, `automation_exercise.yaml`, `campushub.yaml` all went back to their detailed step lists, and `explorer.py`'s prompt/`MAX_ACTIONS_PER_STEP` reverted to the original step-at-a-time framing (byte-identical to before the collapse, confirmed via `git diff`).

**What was checked/modified before accepting:** All 4 domains reload correctly with the restored steps; full backend suite (152 tests) passes.

---

## Broader workflow coverage + add domain knowledge from the dashboard

**Context:** Mentor asked for two things: (1) each registered site should have a broad set of workflows ready to go, not just 2-3, so a spot request during the presentation doesn't need new code; (2) when a ticket comes back "no domain knowledge for this target," there should be a way to supply that knowledge from the dashboard instead of hand-editing a YAML file.

**Prompt:** Expand ParaBank/Toolshop/AutomationExercise with realistic additional workflows (bank account services, checkout, negative-test scenarios, footer/category features actually documented on each real site). Build a real "add domain knowledge" feature: a dashboard page that lists every registered domain/workflow and a form to add a new workflow to an existing domain or register a brand-new one - written straight to the same YAML store the Planner reads, usable by a ticket immediately with no restart.

**What was generated:**
- `parabank.yaml`: +5 workflows (open_new_account, find_transactions, update_contact_info, request_loan, log_out) alongside the existing login/transfer_funds/pay_bill
- `practice_software_testing.yaml`: +4 workflows (view_product_details, search_no_results, filter_by_category, a full checkout)
- `automation_exercise.yaml`: +5 workflows (search_products, category_browse, subscribe_to_newsletter, login_invalid_credentials, write_product_review) - all confirmed against the site's own documented test cases
- `backend/app/domains/manifest.py` - `slugify()` and `save_workflow()`, the write side of the domain knowledge store `load_domains()` already reads: creates a new domain's YAML file or appends/replaces a named workflow in an existing one
- `backend/app/main.py` - `GET /api/domains` (list everything registered) and `POST /api/domains` (add a workflow), both auth-gated, validating that at least one of url_contains/text_contains is given (otherwise nothing could ever verify the workflow) and that a brand-new domain has a base_url
- `frontend/src/pages/DomainKnowledge.tsx` - new page: a form (domain name with autocomplete against existing ones, base URL for new domains, workflow name, a dynamic step list, expected outcome) plus a live list of every registered domain and its workflows. New sidebar nav item + route.

**What was checked/modified before accepting:**
- New unit tests for `slugify`/`save_workflow` (new domain, appending a second workflow, replacing a same-named workflow) and functional tests for both endpoints (success, missing expected_outcome, empty steps, missing base_url on a new domain, unauthenticated) - all against an isolated temp directory, never the real YAML files
- New frontend tests: the page lists registered domains/workflows correctly, rejects a submission with no url_contains/text_contains, and a real submission posts the right payload and shows the success message
- Left CampusHub's YAML untouched - couldn't find a CampusHub repo on the connected GitHub account to read its actual routes/features from (only the empty Vite-scaffold `-arbisoft-internship` repo exists there), so didn't invent workflows for functionality that might not exist
- Full backend suite (163 tests) and frontend suite (18 tests) pass; `tsc`/`oxlint` clean
- **Not yet completed:** same caveat as the earlier domain swap - the new ParaBank/Toolshop/AutomationExercise workflows are sourced from web search against each site's own docs, not a live page load (this sandbox's egress is locked to an allowlist), so still needs a real local run to confirm before relying on them for the presentation

---

## CampusHub verification + expanded coverage

**Context:** The previous round's entry above flagged that CampusHub's YAML was left untouched because no CampusHub repo could be located to verify against - only an empty Vite scaffold was visible at the time. CampusHub's actual source turned out to live on the `week5-mcp-multiagent` branch of `duashakeel0/-arbisoft-internship`, not on its default branch, which is why it wasn't found earlier.

**Prompt:** Find CampusHub's real source and use it to confirm the existing `campushub.yaml` workflows are accurate, then fill it out with more workflows the same way the other three domains were expanded.

**What was generated:**
- Read the real CampusHub frontend source directly (`src/routes/AppRoutes.tsx`, `src/pages/Login.tsx`, `Dashboard.tsx`, `MarkAttendance.tsx`, `Students.tsx`, `Register.tsx`, `src/components/AttendanceForm.tsx`, and the relevant TanStack Query hooks) and the Django models/routes backing it, all read-only - no changes were made to the CampusHub repo itself.
- Confirmed the 3 pre-existing workflows (`student_login`, `mark_attendance`, `view_own_records`) were already 100% accurate against real source - their assertions (`Welcome to CampusHub`, `Attendance marked successfully!`, `Attendance Records`) match the live component text exactly.
- Added `view_students` (login → `/students` → assert `Manage student records here.`), `edit_attendance_record` (create a record, click Edit, change status, resubmit → assert the confirmed toast `Attendance record updated!`), `delete_attendance_record` (create then delete a record → assert the confirmed toast `Attendance record deleted.`), and `login_invalid_credentials` (wrong username/password → assert `Login failed`).
- Deliberately did not add an "add student" or "register new account" workflow, for the same reason registration is excluded from `automation_exercise.yaml`: `Student.student_id` and `User.username` are both `unique=True`/unique in the Django models, so a fixed value only succeeds on the first run.

**What was checked/modified before accepting:**
- Every new assertion is a literal string read directly from CampusHub's source (toast text from the mutation hooks, heading/paragraph text from the page components) - not guessed or inferred, unlike the earlier ParaBank/Toolshop/AutomationExercise round which relied on web search.
- `load_domains()` loads the updated YAML with no schema errors.
- Full backend suite (163 tests) and frontend suite (18 tests) still pass - no code changes were needed outside the YAML itself.

---

## True live video feed + fixing missing red/green boxes

**Context:** The live view only updated once per browser action, and actions can be seconds apart while the model "thinks" or a page loads - so it read as an occasionally-refreshing still image, not a live camera. Separately, the red/green highlight box was frequently just missing: `_element_box` matched a selector against the snapshot list by string equality against `#id`/`[name="..."]` only, so any action targeting an element without an id/name, or a selector built any other way (a class, an attribute, Playwright's own `text=` engine), silently got no box at all.

**Prompt:** "also live testing is being done but its picture slike live screenshots, i want video monitoring like live camera showing also red bloakcs around errors are not there" - make the live view continuously update like real video, and fix the missing highlight boxes.

**What was generated:**
- `backend/app/agents/explorer.py`:
  - `_element_box` rewritten from a static snapshot-rect lookup into an async instance method that asks Playwright directly - `page.locator(selector).first.bounding_box(timeout=1000)` - for whatever the selector currently resolves to on the live page. Works for any selector shape the model can produce, not just a bare id/name match, and returns `None` cleanly (via `PlaywrightError`) if the element is gone, hidden, or the selector never matched anything.
  - New `_live_frame_loop()`: a background `asyncio` task that runs for the whole exploration, capturing and emitting a screenshot every `LIVE_FRAME_INTERVAL_S` (0.75s) independent of the model's action loop - the actual "video" - tagged `"kind": "frame"` so it's clearly not a discrete, report-worthy action. Started in `explore()` only when an `on_action` listener is actually attached (no point paying the screenshot IO for a live view nobody's watching), and cancelled in the existing `finally` block alongside the browser close.
  - `_emit_action`'s events now carry `"kind": "action"` so the two event shapes stay distinguishable downstream.
- `backend/app/agents/pipeline.py` - `on_action`'s wrapper now reads `event.pop("kind", "action")` and uses it as the WebSocket event's own `"type"`, so `"frame"` and `"action"` arrive as distinct event types on the wire with no new endpoint/plumbing needed.
- `frontend/src/types/pipeline.ts` - new `"frame"` variant on the `PipelineEvent` union (`screenshot_url`/`viewport` only, no step/action/target_box - it's purely visual).
- `frontend/src/hooks/usePipelineRun.ts` - a `"frame"` event swaps in the newer screenshot on the current `ActionFrame` (keeping whatever step/selector/box caption the last real action set) without ever touching `frameHistory`, so the filmstrip and the report/PDF's action log stay action-only.
- `frontend/src/components/LiveBrowserView.tsx` + `.css` - a small pulsing "LIVE" badge in the header (only shown once a frame exists) to make the continuous-feed behavior visible, and a fallback caption ("Streaming the browser session…") for the moment before any real action has landed yet.

**What was checked/modified before accepting:**
- New Explorer unit tests: `_element_box` now queries a fake `page.locator(...).bounding_box()` and returns `None` for a selector matching nothing (not just a selector-less action); `_live_frame_loop` emits periodically-tagged `"frame"` events with no `step`/`target_box` fields and swallows a broken listener without dying; a full `explore()` run (fake browser, a step monkeypatched to stall for 50ms) proves the background loop actually ticks concurrently with real work and gets cleanly cancelled afterward, not just wired up syntactically.
- New pipeline unit test: an Explorer that emits both `"kind": "frame"` and `"kind": "action"` events (plus one with no `"kind"` at all, to confirm the default) comes out the WebSocket as the right `"type"` for each.
- New frontend test (`LiveBrowserView.test.tsx`): a successful action renders a green box, a failed one renders a red box with the error text, a frame with no `target_box` (the live-tick case) renders no box at all, and the LIVE badge only appears once a frame exists.
- Full backend suite (168 tests, +5) and frontend suite (22 tests, +4) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed:** needs a real local run against a live site to confirm the 0.75s interval feels genuinely video-like without flooding the WebSocket/UI, and that Playwright's `bounding_box()` behaves the same against real, complex pages as it does against the fake locator in tests.

---

## Longer Ollama timeout + live run surviving navigation

**Context:** Two more real usability bugs. First, Ollama's 180s request timeout was tripping on genuinely slow local hardware mid-run, not just on the "model still loading" case it was sized for. Second, and more disruptive: `Dashboard.tsx` and `RunTest.tsx` each called `usePipelineRun()` themselves, so the WebSocket connection and all live run state (stages, feed, live frames, results) lived inside whichever page component started the run. Navigating to History/Compare/Analytics mid-run unmounted that page, which tore down the socket and threw away every bit of live state - coming back showed a blank dashboard as if no test had ever run, even though the backend run itself was likely still going.

**Prompt:** "upgrade llama timeout so it doesnt timeout, make it 10 minutes maybe" / "when i run a test, and go to any other nav... test got vanishes... fix it in a way, if i might change nav, test still keep running."

**What was generated:**
- `backend/app/agents/ollama_client.py` - `REQUEST_TIMEOUT_SECONDS` raised from 180 to 600 (10 minutes).
- `frontend/src/contexts/PipelineRunContext.tsx` (new) - a `PipelineRunProvider` that calls `usePipelineRun()` exactly once and shares it via context, plus a `usePipelineRunContext()` hook (same throws-outside-provider pattern as `AuthContext`).
- `frontend/src/App.tsx` - `PipelineRunProvider` now wraps `<BrowserRouter>` itself (inside `AuthProvider`, above every `<Route>`), so it's never part of the tree that unmounts on navigation - only the routed page underneath it swaps.
- `frontend/src/pages/Dashboard.tsx` and `RunTest.tsx` - both switched from `usePipelineRun()` to `usePipelineRunContext()`, so they now read and drive the exact same live run instead of each tracking an independent one (a pre-existing but separate inconsistency - starting a run from one page never used to show up on the other either).

**What was checked/modified before accepting:**
- New `PipelineRunContext.test.tsx`: a consumer used outside the provider throws the expected error; two consumer trees mounted in sequence under the same still-alive provider (simulating navigating to a different page mid-run, via a `rerender` that swaps children under the identical provider instance) see the exact same live `status`, and only one `WebSocket` ever got opened - proving the connection is genuinely shared and survives what would previously have been a remount, not just that the code compiles.
- Full backend suite (168 tests) and frontend suite (24 tests, +2) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed:** same as before - no real Ollama instance or live browser session in this sandbox to confirm a genuinely slow local run now survives past 180s, or that navigating away and back mid-run behaves as expected against the real WebSocket (only a faithful fake was exercised in tests).

---

## Keeping Ollama warm between calls (keep_alive)

**Context:** A real screenshot showed the exact 180s timeout message firing on the Explorer's very first action of a run - the model-load-time case the timeout was already sized to tolerate, not a genuinely stuck request. Raising the timeout (previous entry) stops that from failing the run, but doesn't make Ollama any faster; the actual fix for the underlying slowness is not paying the multi-minute model-load penalty repeatedly in the first place. Ollama's own default unloads a model from memory 5 minutes after its last call - so any gap between actions on a slow step, or between separate demo runs while explaining something to a mentor, was enough to force a full reload on the next call.

**Prompt:** "whats the reason of this, i cant understand / also is there any way to fasten ollama, its so slow / my mentor said it would piss my panel board... can we pls fix it."

**What was generated:** `backend/app/agents/ollama_client.py` now sends `"keep_alive": "30m"` on every `/api/generate` request (configurable via a new `OLLAMA_KEEP_ALIVE` env var, documented in `.env.example`) - tells Ollama to keep the model resident in memory for 30 minutes after each call instead of its 5-minute default, so a normal gap between actions or between tickets during a demo doesn't trigger a reload.

**What was checked/modified before accepting:**
- New Ollama client unit tests: `keep_alive` is sent with the documented default, and is overridable via `OLLAMA_KEEP_ALIVE`.
- Full backend suite (170 tests, +2) passes.
- **Not yet completed, and explained plainly in chat:** `keep_alive` only prevents *repeated* reloads - it can't make the very first call (a cold Ollama server, nothing loaded yet) faster, and it can't speed up per-token generation on slow CPU hardware. For that, the real levers are outside this codebase: pre-warm Ollama once before a demo (`ollama run llama3.1 "hi"`), confirm it's actually using a GPU if one exists (`ollama ps`), or switch `OLLAMA_MODEL` to a smaller/faster model (e.g. `llama3.2:3b`) at the cost of some decision accuracy - a real tradeoff for the user to weigh, not something to change unilaterally.

---

## Switching the default model to llama3.2

**Context:** Asked to check the output of a real `ollama ps` run - it showed `PROCESSOR: 100% CPU` with no GPU listed, running llama3.1 (8B, Q4_K_M). That confirms the earlier "switch to a smaller model" suggestion wasn't a hypothetical - this machine is genuinely compute-bound on CPU, where model size is the single biggest lever on speed. Given the go-ahead ("ok switch if u think if would be faster"), made the change instead of just describing it.

**What was generated:** `backend/app/agents/ollama_client.py`'s `DEFAULT_MODEL` and `.env.example`'s `OLLAMA_MODEL` both changed from `llama3.1` to `llama3.2` (its default tag is the 3B variant - roughly a third the compute per token of the 8B model), with a comment explaining the CPU-bound tradeoff and how to check it (`ollama ps`) and revert (`llama3.1`) if selector-picking accuracy matters more than speed for a given run.

**What was checked/modified before accepting:**
- No test asserted the specific default model string, so nothing needed updating beyond the constant/env template themselves.
- Full backend suite (170 tests) still passes.
- **Not yet completed, and told plainly to the user:** this only takes effect once they run `ollama pull llama3.2` and either remove `OLLAMA_MODEL` from their real local `.env` (not the tracked `.env.example`) or set it to `llama3.2` explicitly - their `ollama ps` output showed llama3.1 already loaded from an existing local `.env`/prior pull, which this code change can't reach or edit. Also genuinely can't verify from this sandbox that 3B is meaningfully faster on their exact hardware or still accurate enough for the harder workflows (ParaBank's multi-field forms especially) - worth a real comparison run before relying on it for the actual presentation.

---

## Skipping a redundant first-step LLM call (llama3.2 hallucinated selector)

**Context:** A real screenshot after switching to llama3.2 showed a new, different failure than the timeout ones - `click on #home` failing with `Timed out waiting for '#home'`. `#home` doesn't exist on ParaBank's page at all; the step was "Navigate to the ParaBank homepage," a navigation-only step whose prompt explicitly says "if already on the right page, respond done, don't interact with anything" - and `explore()` had already `goto()`'d `domain.base_url` (ParaBank's homepage) before this step's first decision was even asked for. llama3.2 ignored the instruction and invented a click anyway. This is exactly the accuracy cost flagged when switching models, showing up for real.

**Prompt:** shown the screenshot, asked "whats the reason of this... its still saying this."

**What was generated:** `backend/app/agents/explorer.py`'s `explore()` now checks, only for the very first step of a workflow: if that step is navigation-only (per the existing `_is_interactive_step`) and the browser's current URL already equals `domain.base_url` (true here, since `goto()` just put it there and nothing else has happened yet), the step is skipped entirely - no model call at all, so there's nothing for the model to hallucinate against. Deliberately narrow: only applies to the first step, and only when the URL genuinely already matches - a later "Navigate to X" step that legitimately needs a click to get there (e.g. following a nav link to a page not yet visited) still goes through the normal model-decides-the-action path untouched.

**What was checked/modified before accepting:**
- Confirmed against the real, already-fixed regression test for the opposite case (`test_execute_step_reinterprets_navigate_with_selector_as_click`, from Day 6/7's the_internet/dropdown loop fix) that a "Navigate to X" step still executes a real click when the browser *isn't* already at the destination - a first cut at this fix wrongly special-cased every non-interactive-step action inside `_execute_step` itself, which broke exactly that case; caught by the existing test suite before it was accepted, and reverted in favor of the narrower `explore()`-level check.
- New Explorer tests: the redundant first step (browser already at `domain.base_url`) never reaches `_execute_step` (so never makes an LLM call); a first step where `goto()` landed somewhere else (simulating a redirect) is NOT skipped and still goes through the normal decision path.
- Full backend suite (172 tests, +2) passes.
- **Not yet completed:** can't verify against the real live ParaBank page from this sandbox whether `goto()` lands on an URL that string-matches `domain.base_url` *exactly* (a redirect adding a session param, for instance, would silently fall back to the old model-decides behavior rather than break anything) - worth confirming on a real run.

---

## Groq as an alternative Ollama backend

**Context:** Even with the earlier fixes (longer timeout, keep_alive, llama3.2, redundant-step skip), running an LLM on CPU-only local hardware is inherently slower than a cloud API - that's an expected limitation, not a bug, but still a real problem for a live demo. Asked whether Ollama could be connected some other way instead of running on the user's own device.

**Prompt:** "is it possible to connect ollama in any other way rather than running it on my device" - offered two paths (rent a GPU cloud box and point OLLAMA_HOST at it, needing no code; or add a Groq-backed client for genuinely fast hosted inference, needing new code) and asked which. Chose the Groq client.

**What was generated:**
- `backend/app/agents/groq_client.py` (new) - `GroqLLMClient`, hitting Groq's OpenAI-compatible `/chat/completions` endpoint (Bearer auth, `response_format: json_object` for the same JSON-only contract every prompt in this project relies on). Deliberately kept `provider = "ollama"` rather than introducing a real "groq" provider concept - it's a drop-in backend for the same free/local-model comparison arm, so every existing report/history-stats/frontend path (which only knows "claude" and "ollama") keeps working with zero changes. The actual model name (`llama-3.1-8b-instant` by default) still shows up wherever a run's timings are displayed, so nothing is hidden from the report.
- `backend/app/agents/pipeline.py`'s `make_llm()` - a new `OLLAMA_BACKEND` env var (default `"local"`) switches the "ollama" slot between `OllamaLLMClient` and `GroqLLMClient` - opt-in only, so nothing changes for anyone who doesn't set it.
- `.env.example` - documents `OLLAMA_BACKEND`, `GROQ_API_KEY`, `GROQ_MODEL`.

**What was checked/modified before accepting:**
- New Groq client unit tests (mirroring the Ollama client's own test shape): correct text/token-count parsing, Bearer auth header, JSON-mode request body, missing-API-key error, env-configurable model, HTTP-error/timeout/connection-error/malformed-response all raising a clean `LLMError`.
- New pipeline test: `make_llm("ollama")` returns the local client by default, and the Groq client only once `OLLAMA_BACKEND=groq` is explicitly set - and confirms the returned client's `provider` is still `"ollama"`, not a new value.
- Full backend suite (183 tests, +11) passes.
- **Not yet completed:** no real Groq API key available in this sandbox to verify against Groq's actual live API (only the shape of its documented OpenAI-compatible endpoint) - worth a real run once the user has a free Groq key to confirm both the request/response format and that it's actually meaningfully faster on their hardware.

---

## Loop guard was failing a step that had actually already succeeded

**Context:** After switching to Groq (confirmed genuinely ~10x faster in a real run - 85s total vs. multi-minute local runs), a real report showed a *new* failure: a Toolshop login run failed with "Explorer repeated the same action 3 times on step 'Enter customer@practicesoftwaretesting.com into the Email field' (fill on '#email') - stopping to avoid a loop," at 100% action accuracy. The fill genuinely succeeded every single time (Playwright had no trouble with it) - the model just kept re-issuing the exact same already-successful fill instead of recognizing the step was done and moving on, despite the prompt's history block explicitly saying "do not repeat one that already succeeded." Same accuracy-vs-speed tradeoff as the earlier hallucinated-selector case, different symptom: this time the model wasn't wrong about *what* to do, just failed to recognize *when to stop*.

**Prompt:** shown the report, "speed is 10x better but" [this failure].

**What was generated:** `backend/app/agents/explorer.py`'s `_execute_step` now checks, before the identical-action loop guard: if the model's current decision exactly matches an action that already *succeeded* earlier this step, treat it as implicit "done" instead of re-executing it or letting it count toward the loop guard. This splits what the loop guard used to treat as one case (any repeated identical action = suspicious, fail after 2 repeats) into the two genuinely different situations it actually covers: a step repeatedly *failing* the same way is still a real stuck loop and still raises `ExplorerError` exactly as before; a step repeatedly *re-doing something that already worked* is virtually always the model failing to notice completion, not a real problem, so it now completes gracefully instead of failing the whole exploration over something that was never actually stuck.

**What was checked/modified before accepting:**
- The existing loop-guard regression test (`test_execute_step_raises_after_repeating_same_action`) turned out to assert the *old*, less correct behavior - it used a fake action that always "succeeds," so under the new logic it would complete gracefully instead of raising. Renamed/updated it to `test_execute_step_raises_after_repeating_same_failing_action` with a genuinely failing fake action, so it still validates the case that actually matters (a truly stuck step) instead of accidentally locking in the bug being fixed.
- New test (`test_execute_step_completes_when_repeating_an_already_succeeded_action`) reproduces the exact real Toolshop failure - 3 identical successful fills queued, only the first is ever executed, the step completes cleanly rather than raising.
- Full backend suite (184 tests, +1 net - one renamed/fixed, one new) passes.
- **Not yet completed:** same as always with model-quality issues - this closes one specific recurring pattern (repeating an already-successful action) but doesn't make the model itself more reliable in general; a different kind of confusion could still surface on a different step shape. Worth another real run to confirm this exact failure is gone and watch for anything new.

---

## Groq's free-tier rate limit

**Context:** After fixing the API-key setup and the already-succeeded loop-guard bug, a real run hit a third, different failure: `Groq returned HTTP 429: Rate limit reached for model llama-3.1-8b-instant... on tokens per minute (TPM): Limit 6000, Used 4757, Requested 3223.` This is a direct, almost funny consequence of the speed fix working: local Ollama was slow enough to naturally pace out the Explorer's rapid per-action calls, but Groq answers almost instantly, so a real run blows through the free tier's per-minute token budget in seconds. The client had no retry logic at all, so hitting this even once failed the whole step (and often the whole exploration) outright - even though Groq's own error message says exactly how long to wait (`try again in 19.8s`).

**Prompt:** shown the report - "everytime its linke with ollama, im so done."

**What was generated:** `backend/app/agents/groq_client.py`'s `complete()` now retries up to `MAX_RATE_LIMIT_RETRIES` (3) times on a 429, waiting however long Groq says to wait (parsed from the `Retry-After` header if present, else the "try again in Xs" text in the error body, plus a small buffer) before retrying - instead of failing on the very first rate-limit hit. Only 429s are retried; every other error (auth, malformed response, genuine timeout) still fails immediately as before.

**What was checked/modified before accepting:**
- New tests: a 429 followed by a successful retry completes normally and slept the parsed wait time; a persistently rate-limited run still eventually gives up cleanly after the retry budget (not an infinite retry loop against a genuinely exhausted quota); the wait-time parser is tested directly against both the header and the error-body-text cases, plus a sensible fallback when neither is parseable.
- Fixed an existing test (`test_non_200_response_raises_llmerror`) that happened to use a 429 fixture - switched it to 500 so it still tests the generic non-200 path without accidentally exercising (and being slowed down by) the new retry logic.
- Full backend suite (188 tests, +6 net) passes.
- **Not yet completed:** can't verify against Groq's real rate limiter from this sandbox - the retry math (parsing "try again in Xs", waiting that long) is confirmed correct in isolation, but only a real run against a real exhausted quota confirms the whole exploration actually recovers smoothly instead of just failing slower. Also worth the user knowing this is a genuine free-tier ceiling, not a bug to fully eliminate - a workflow with a lot of steps in quick succession could still hit it more than 3 times in a row on a very busy account, at which point the run will fail with a clear rate-limit message rather than hang forever.

---

## Rejecting fill/select/press on a navigation-only step

**Context:** A real Toolshop login run showed the model filling the login email into the page's search bar instead of navigating to /auth/login. The first step, "Navigate to /auth/login," is navigation-only - the prompt explicitly says not to interact with anything for this step. But that destination isn't the site's homepage, so the earlier deterministic skip (which only fires when the step's destination is exactly domain.base_url) didn't apply here; the model had to genuinely decide how to navigate, and instead of a real "navigate" action it typed real text into whatever input the page had. Same underlying instruction-following gap as the earlier hallucinated "#home" click, but this time the model chose "fill" instead of "click," and there was no existing guard against that action type on this step shape.

**Prompt:** "its filling eail in search barr."

**What was generated:** `backend/app/agents/explorer.py`'s `_execute_step` now deterministically rejects "fill"/"select"/"press" whenever the current step is navigation-only, before the action is ever attempted against the real page. This is narrower and safer than the earlier reverted attempt to block *all* non-"done" actions on non-interactive steps (which wrongly broke the case where a "navigate to X" step legitimately needs a click on a link) - fill/select/press specifically can never accomplish "get to a different page" regardless of which element they target, unlike click (can follow a link) or navigate (goes there directly), so rejecting only those two action types is unconditionally correct, not just usually correct. Recorded as a failed attempt (not silently dropped) so the model sees exactly why on its next decision, via the existing action-history block in the prompt.

**What was checked/modified before accepting:**
- New test reproduces the exact failure: a queued `fill` on a "Navigate to /auth/login" step is rejected without ever reaching Playwright, recorded as a failed action with a clear reason, and the subsequent real `navigate` decision executes normally and completes the step.
- Confirmed the existing dropdown-click regression test still passes unaffected (it uses "click," which this change never touches).
- Full backend suite (189 tests, +1) passes.
- **Not yet completed:** this closes the specific case of fill/select/press being used where only navigate/click ever could work - it doesn't prevent the model from picking the *wrong* selector for a legitimate click/navigate on this step type, which is the same general model-accuracy ceiling flagged repeatedly. Worth another real run to confirm this exact failure is gone.

---

## Rewriting the auth/login step to remove URL-construction ambiguity

**Context:** Belt-and-suspenders on top of the deterministic code fix above. The step read "Navigate to /auth/login" - a relative path, requiring the model to combine it with the domain's base URL itself (inferred from the current page's URL, since it's not stated outright anywhere in the prompt) to build the real "navigate" action's value. That's exactly the kind of small extra reasoning step a fast/weaker model can skip or botch, which is plausibly part of why it reached for the search bar instead in the first place.

**Prompt:** "listen to me write auth/login steps again for ollama, pls make sure everything is correct."

**What was generated:** `backend/app/domains/data/practice_software_testing.yaml` - the `login` and `checkout` workflows' first step changed from "Navigate to /auth/login" to "Navigate to the URL https://practicesoftwaretesting.com/auth/login (a direct page navigation - do not use the search bar or any other field on the page)" - the full absolute URL spelled out directly, plus an explicit reminder of what this step is (and isn't). Kept the literal "Navigate to" prefix at the very start on purpose - `_is_interactive_step()`'s classification (which controls both the nav_hint and the new fill/select/press rejection above) matches on that exact prefix; an earlier draft phrased it "Navigate directly to the URL..." which would have silently broken that classification and made things worse, caught before committing by directly testing `_is_interactive_step()` against the new text.

**What was checked/modified before accepting:**
- Directly verified `ExplorerAgent._is_interactive_step()` still returns `False` for the new step text before accepting it.
- `load_domains()` loads the updated YAML with no schema errors.
- Updated `test_planner.py`'s hardcoded end-to-end assertion (it asserted the real manifest's exact step text, since `PlannerAgent` always calls the real `load_domains()`) to match.
- Full backend suite (189 tests) passes.
- **Not yet completed:** left `contact_us`'s "Navigate to /contact" (same relative-path pattern, same theoretical risk) untouched - the user's request was specifically about auth/login; happy to apply the same treatment there and to the other domains' relative-path navigate steps if wanted, but didn't do it unprompted.

---

## Case-sensitive id near-miss (#Email vs. #email)

**Context:** A real run after the previous fix showed genuine progress - it navigated to the login page correctly this time - but then failed the next step: `fill on #Email — Timed out waiting for '#Email'`. The real element's id is (almost certainly) lowercase `email`; the model wrote `#Email`, echoing the capitalization of the step's human-readable label ("the Email field") instead of the actual id it was shown in the snapshot. CSS id selectors are case-sensitive, so a wrong-case guess fails outright even though it's obviously meant to be that exact element - the existing bare-id correction (`_resolve_selector`) didn't catch this because it only fires for a selector with no `#`/`.`/etc prefix at all; `#Email` already "looks like" a real CSS selector so it sailed through unchanged.

**Prompt:** "youve clearly written write this in email field, isk why its nt getting it."

**What was generated:** `_resolve_selector` now also checks any plain `#some-id`-shaped selector (nothing more elaborate - no combinators/attributes/spaces, so it never touches a genuinely complex selector) against the snapshot: if there's no exact-case id match but there IS a case-insensitive one, the selector is corrected to the real casing before Playwright ever sees it.

**What was checked/modified before accepting:**
- New tests: `#Email` against a snapshot with a real `email` id resolves to `#email`; an exact-case match is left alone; a selector with no case-insensitive match anywhere in the snapshot (nothing to correct it to) is left exactly as given rather than guessed at.
- Confirmed the existing "leaves a real CSS selector alone" test still passes - a bare-id-shaped selector with no near-miss in the snapshot falls through unchanged, same as before.
- Full backend suite (192 tests, +3) passes.
- **Not yet completed:** same general caveat as every accuracy fix so far - this closes one specific, common near-miss (case-only mismatch on an otherwise-correct id), not selector accuracy in general. A completely wrong id, or a case mismatch combined with something else off, would still fail. Worth another real run to see how far through the workflow it gets now.

---

## Redesigning the report to look like a real QA test report

**Context:** After several rounds of chasing model-accuracy bugs (and deciding to move on from Ollama debugging for now), turned to the actual deliverable: the downloadable PDF and on-screen report were functionally complete (verdict, findings, metrics, a couple of charts, screenshots) but read as an ad-hoc data dump rather than a QA report anyone would recognize as one - no step-by-step test case table, no expected-vs-actual block, no pass/fail visual summary, generic section ordering.

**Prompt:** "these reports are so basic, make them exactly how QA testing reports look like, but keep tables charts and graphs in it."

**What was generated:**
- `backend/app/pdf_report.py` - restructured into standard, numbered QA report sections: (1) Test Information (ticket, module/feature under test, test type, model/agent, timing, cost, overall result), (2) Test Execution Summary (a pass/fail donut chart of actions attempted, alongside a counts table - total/passed/failed/skipped steps, pass rate), (3) Expected vs. Actual Outcome (the workflow's `expected_outcome` rendered in plain English next to the Verifier's actual explanation and result), (4) Summary & Analysis (the existing Claude-written narrative, kept), (5) **Test Case Execution Details** - the core addition: a real step-by-step table (Step #, the exact step text, PASS/FAIL/SKIPPED/NOT REACHED, a short note) built entirely from `plan.steps` cross-referenced against the real action log, not fabricated - a step with zero actions reads "skipped" only if the whole run completed (the deterministic first-step homepage skip from earlier), otherwise "not reached", (6) Quality Metrics (existing bar chart, kept), (7) Defects/Findings (existing table, now with auto-numbered `DEF-001`-style IDs), (8) Stage Timings (kept), (9) Evidence/Screenshots (kept).
- `frontend/src/components/ReportCard.tsx` - added the same two new sections to the on-screen card: a "Test Execution Summary" reusing the dashboard's own `DonutChart` component (visual consistency, not a new chart style) for actions passed/failed plus a small stats grid, and a real "Test Case Execution Details" `<table>` (Step #/Description/Status/Notes) built by a `buildStepRows()` helper that mirrors the PDF's Python logic exactly, so the on-screen view and the downloaded PDF never disagree about what happened.

**What was checked/modified before accepting:**
- Rendered a full sample PDF locally (via `Read` on the generated file, which can view a PDF's rendered pages directly) and eyeballed the actual layout, not just "did reportlab throw" - confirmed the numbered sections, table alignment, donut/bar charts, and color-coded statuses all render as intended before calling it done.
- New backend tests: `_format_expected_outcome` for both-fields/none/empty; `_step_rows` for all four statuses (pass, fail, skipped-because-completed, not-reached-because-incomplete) and confirms deliberate broken-input probes are excluded from step status (never mistaken for a real failed attempt); a full realistic-fixture `build_pdf` smoke test exercising every new section together, not just an empty/minimal run.
- New frontend tests: the step table renders real step text and computes SKIPPED vs PASS vs FAIL correctly from the action log; the Test Execution Summary donut appears once metrics exist and is absent when they don't (an unmatched/pre-metrics report shouldn't show an empty chart).
- Full backend suite (198 tests, +6) and frontend suite (28 tests, +4) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed:** haven't seen this rendered against a real completed run with real screenshots/findings/multiple steps in the actual browser dashboard - the sample PDF and the component tests both use hand-built fixtures, not a live pipeline result.

---

## Mentor-checklist audit + chatbot ticket-launch + per-site test counts

**Context:** Given a long, dense mentor checklist covering nearly every part of the project and asked to check what was actually missing before a sync, rather than take the checklist at face value. Actually verified each contested item against the real codebase (backend coverage run live, E2E test file confirmed to exist, comparison dashboard fields grep'd, Trello comment content read directly, GlobalChat's actual capabilities checked) instead of assuming. Two lines in the same message directly contradicted each other ("remove ollama from Explorer" vs "apply both LLMs... 3 reports") - flagged rather than guessed, and the user confirmed: keep both models, one combined report page is fine as already built.

**What the audit found:** most of the checklist was already genuinely done (91% backend coverage, real E2E test, comparison dashboard already shows a winner-per-metric and missed-steps, Trello comments already include pass/fail/reason/error/summary, ModelSelector already offers Claude/Ollama/Both). Three real, confirmed gaps: no frontend test coverage tooling installed at all, no "tested this site N times" summary, and the chat widget being pure Q&A with no way to actually start a test run.

**Prompt:** "fix AI chatbot, it should run tickets and answer me about the system its built in" / "yes add count summary."

**What was generated:**
- `frontend/src/App.tsx` - restructured so `GlobalChat` renders as a sibling of `<Routes>` inside `<BrowserRouter>` (a new `AppShell` component), not nested inside `DashboardLayout` (which used to remount per route). Needed because the chat can now navigate the user to the dashboard when it starts a run - without this move, that navigation would have unmounted the chat panel and wiped the conversation, the same bug class `PipelineRunProvider` fixed earlier for the live run itself.
- `backend/app/main.py`'s `/api/chat` - the model now responds with structured JSON (`intent`: "chat" or "run_ticket", plus `ticket_id`/`model`/`reply` for the latter) instead of free prose, so the endpoint can detect "run ticket ABC123" and return an explicit action for the frontend to act on. Also grounded the prompt in real, current facts about the system (the actual four-agent architecture, real tech stack, and the live registered-domains list pulled from `load_domains()`) instead of generic "AI QA dashboard" filler, so questions about how the system works get accurate answers.
- `frontend/src/components/GlobalChat.tsx` - on a `run_ticket` response, calls the shared `usePipelineRunContext().start()` (the exact same function a manual "New Test" submit uses) and navigates to `/`, so a run started via chat is a real pipeline run, not a chat pretending to test something.
- `backend/app/history/schema.py`/`store.py`/`main.py` - new `SiteStats` (domain, run_count, passed, failed, last_tested_at) and `GET /api/history/site-stats`, grouped by domain from the existing `runs` table.
- `frontend/src/pages/Dashboard.tsx` - a new "Sites Tested" sidebar panel showing each registered site's run count ("N×"), pass/fail split, and last-tested date.

**What was checked/modified before accepting:**
- New backend tests: chat's run_ticket JSON is parsed and returned as a structured action; a missing ticket_id in that JSON is correctly treated as a plain chat fallback, not a broken run attempt; a plain-prose (non-JSON) response still works via a graceful fallback; the prompt is confirmed to actually contain real registered domain names, not just claim to. New `site_stats` tests at both the store and endpoint level, including that unmatched (domain-less) runs are correctly excluded from the per-site counts.
- New frontend tests for `GlobalChat`: a plain chat reply never navigates; a `run_ticket` response both opens a real WebSocket (proving the run genuinely started, not just displayed a message) and navigates to `/`; a failed chat request still shows an error. Hit a real jsdom gap along the way (`scrollIntoView` isn't implemented at all in jsdom) - fixed once in the shared test setup rather than per-test, and a real mock-completeness bug (the chat test's `vi.mock` of `services/api` initially omitted `getPipelineSocketUrl`, which `usePipelineRunProvider` also imports from that module - would have made every test relying on `start()` fail opaquely).
- Full backend suite (206 tests, +8) and frontend suite (31 tests, +3) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed:** frontend test coverage tooling (`@vitest/coverage-v8`) still isn't installed - flagged in the audit but not yet fixed, since it wasn't part of what was asked for in this round. The chat's ticket-detection is still an LLM call, not a hardcoded parser - a genuinely ambiguous message could still occasionally misfire (treat a real question as a run request or vice versa); no real Claude account was available in this sandbox to verify the actual detection accuracy on live, varied phrasing.

---

## False FAIL verdict + alarming red styling on a deliberate broken-input probe

**Context:** A screenshot of a real `search_no_results` Toolshop run showed both Claude and Ollama's live browser views rendering a red "failed" caption on an action, yet the report card underneath showed contradictory data for the same run: a FAIL badge next to "100% Actions passed / Passed (2) / Failed (0)." Two separate bugs turned out to be stacked on top of each other.

**Prompt:** "both llms giving same error although test passed showing no results / fic it" (with the screenshot).

**What was generated:**
- `backend/app/agents/verifier.py`'s `_check_assertion` - the actual false-FAIL root cause. `text_contains` matching was case-sensitive, so the workflow YAML's `expected_outcome.text_contains: "No results"` (capital N) never matched the real page's actual text, `"...there are no results."` (lowercase, mid-sentence) - an assertion that was clearly satisfied still failed the whole run. Fixed by lowercasing both sides of the comparison for `text_contains` only; `url_contains` deliberately stays case-sensitive since a URL's exact casing (path segments/slugs) can be meaningful in a way a human-written sentence's capitalization isn't.
- `backend/app/agents/explorer.py`'s `_emit_action()` - the misleading-red-styling root cause. The already-existing `is_broken_input_attempt` flag was captured correctly on the persisted `ActionLogEntry`, but was never included in the dict sent over the live WebSocket, so the frontend had no way to tell a deliberate "try invalid input first" probe (expected to fail/be rejected by design) apart from a genuine action failure - both rendered identically as a red, alarming "failed" box/caption. Threaded the flag through `_emit_action()`'s emitted event (both call sites: the normal action path and `_attempt_broken_input`'s own call).
- `frontend/src/types/pipeline.ts` / `usePipelineRun.ts` - carried the new `is_broken_input_attempt` field from the WS event through to `ActionFrame`.
- `frontend/src/components/LiveBrowserView.tsx` - new `frameTone()` helper returning `"pass" | "fail" | "probe"` (probe takes priority over the raw success flag). A probe frame now renders with a neutral amber `box-probe` outline and a small "Testing invalid input" tag instead of the red `box-fail` styling and error text a real failure gets; the caption never shows the raw error string for a probe either, since failing is the expected/correct outcome, not something to alarm about.

**What was checked/modified before accepting:**
- New backend tests: `_check_assertion` with a case-mismatched `text_contains` in both directions (capitalized expectation against lowercase real text, and vice versa) now passes, confirmed `url_contains` case sensitivity is unchanged, and confirmed a genuinely absent phrase still fails regardless of case. A normal action's emitted live event now asserted to carry `is_broken_input_attempt: False`; a new dedicated test for `_attempt_broken_input` confirms its emitted live event carries `is_broken_input_attempt: True`, not just the persisted `ActionLogEntry`.
- New frontend test: a broken-input-probe frame gets `box-probe` (never `box-fail`), shows the "Testing invalid input" tag, and does not get the `live-browser-caption-fail` class the way a real failure does.
- Full backend suite (211 tests, +5) passes; full frontend suite (32 tests, +1), `tsc --noEmit`, and `oxlint` all clean.
- **Not yet completed:** only `text_contains` was made case-insensitive - if a workflow's assertion turns out to have a case-sensitivity problem in some other field or a different kind of mismatch (whitespace, punctuation), that's a separate bug to diagnose if/when it shows up on a real run.

---

## Dashboard hero: drop the agent-name chips, fix the "enter a URL" copy

**Context:** The dashboard's welcome header showed four separate pill chips reading "Planner / Explorer / Verifier / Reporter" - internal agent names with no real meaning to someone using the tool, reading as clutter rather than a real status indicator. The welcome copy underneath also said "Enter a URL or connect a Trello ticket to get started," but the Start-a-new-test panel only ever had a Trello ticket ID field - there's no URL input anywhere on the dashboard, so that half of the sentence was simply untrue.

**Prompt:** "remove these agent names from hre , else addd smth else , jo think would make it look more proffessional and nice / also if i can check url here then fine , otherwise remove 'add url' from welcome message" (with a screenshot of the four chips).

**What was generated:**
- `frontend/src/pages/Dashboard.tsx` - removed `AGENT_READY_ROW` and its four-chip row entirely. Replaced with a single `dash-hero-status` pill: a small pulsing green dot + a shield-check icon + "4 AI agents online" - one real status readout instead of four unexplained internal names, in the same visual language (pill, border, accent color) the page already uses elsewhere (`dash-hero-eyebrow`). Trimmed the welcome paragraph to "Connect a Trello ticket to get started," dropping the "Enter a URL or" clause since there genuinely is no URL field on this page.
- `frontend/src/pages/Dashboard.css` - replaced `.dash-hero-agent-row`/`.dash-hero-agent-chip`/`.dash-hero-agent-dot` with `.dash-hero-status` (pill styling matching the eyebrow badge) and a `dash-hero-status-pulse` keyframe animation (mirrors the existing "LIVE" dot pulse pattern already used in `LiveBrowserView.css`), respecting `prefers-reduced-motion`.

**What was checked/modified before accepting:**
- Grepped for any other reference to the removed `AGENT_READY_ROW`/`dash-hero-agent-*` classes - none found, safe to delete outright rather than leave dead CSS.
- `tsc --noEmit` clean, full frontend suite (32 tests) still passes, `oxlint` clean (only the two pre-existing unrelated warnings).
- **Not yet completed:** purely a visual/copy change with no new interactive element - didn't add a URL-entry option since one doesn't exist on this page and wasn't asked for, just removed the inaccurate claim that it does.

---

## Explorer steps failing with "Claude's response contained no text content"

**Context:** A real Automation Exercise run (`browse_and_add_to_cart`) showed only 2/4 steps reached and a 33% pass rate on Claude specifically - not an Ollama-only problem, ruling out anything model-provider-specific. The report's finding named the exact error: `Claude's response contained no text content`, repeated until the step exhausted its whole action budget.

**Prompt:** shared the report card directly - "even claude isnt doing t" (referring to the earlier worry that only Ollama was unreliable).

**What was generated:**
- `backend/app/agents/explorer.py` - `DECISION_MAX_TOKENS` raised from 200 to 600. Root cause: `claude_client.py`'s response parsing already anticipated a non-text block (e.g. reasoning) appearing ahead of the real answer, but 200 tokens left no real headroom for that plus the actual JSON decision - the entire budget was sometimes spent before any text existed, producing this exact error, and because the Explorer retries the *same* step on the *same* tight budget, it reliably failed every one of the 6 allotted attempts in a row instead of just once.
- `backend/app/agents/claude_client.py` - when no text block is found, the error now names *why* when it's diagnosable: if `stop_reason == "max_tokens"`, the message explicitly says the response was cut off before any text was produced and suggests raising `max_tokens`, instead of just the bare fact with no lead on the cause.
- `backend/app/agents/verifier.py` - `_explain()`'s two `max_tokens=200` calls (initial + retry) bumped to 400 for the same reason, even though this path already degrades gracefully to `inconclusive` rather than failing the whole run.

**What was checked/modified before accepting:**
- New tests: a response with only a non-text block and `stop_reason="max_tokens"` raises the enriched "cut off by max_tokens" message; the same response shape with a different `stop_reason` (`end_turn`) does *not* get that hint, confirming it's only shown when actually diagnosable rather than guessed at.
- Full backend suite (211 tests, +2) passes.
- **Not yet completed:** this fixes the *symptom* (too little budget, unhelpful error) but the underlying question of exactly why Claude sometimes spends tokens on non-text content before the real answer here is still open - worth another real run to confirm 600 tokens is enough headroom, and worth revisiting if the same error resurfaces even at the higher budget.

---

## A passing workflow reported as FAIL, blamed on an unrelated probe error

**Context:** After the max_tokens fix above, a real Automation Exercise `contact_us` run came back FAIL with 100% of the actual workflow's actions passing (6/6) - the finding's "Error message" read `Claude's response contained no text content`, the same string from the previous round's fix, which made it look like the fix hadn't worked. It had; this was a second, different bug hiding behind the first.

**Prompt:** shared the new report card directly, no further comment needed - the contradiction (100% actions passed, verdict FAIL, an LLM error as the stated cause) was the whole signal.

**What was found (two separate bugs):**
1. `backend/app/agents/reporter.py`'s `_error_message()` picked the *last failed action's error* as the fallback reason for a finding, with no filter for `is_broken_input_attempt`. The workflow's own deliberate negative-input probe (which is *supposed* to sometimes fail/error, and is correctly excluded from `verification.warning_count` by `verifier.py`'s own `_count_errors`) had itself hit the "no text content" LLM error - and because it was the *last* failed action in the log, its unrelated error got surfaced as the reason a completely different, real assertion failure happened.
2. `backend/app/browser.py` never handled JS `dialog` events. Automation Exercise's real Contact Us form gates its submission behind a native `confirm()` dialog - Playwright auto-dismisses (cancels) any dialog with no listener, so the Explorer's click on Submit genuinely succeeds but the page never reaches its actual result, and the real "Success!" assertion correctly fails for a reason that has nothing to do with the workflow being wrong.

**What was generated:**
- `reporter.py`'s `_error_message()` now excludes `is_broken_input_attempt` actions from its fallback, matching `verifier.py`'s existing convention exactly.
- `browser.py`'s `BrowserSession.start()` now registers a `page.on("dialog", ...)` handler that accepts every dialog - the closest match to what a real user clicking "OK" would do.

**What was checked/modified before accepting:**
- Couldn't reach automationexercise.com from this sandbox to verify the dialog theory live (network policy blocks general external browsing here) - built a local HTML fixture (`tests/e2e/fixtures/confirm_dialog_form.html`) reproducing the exact same confirm-then-reveal-success pattern instead, and proved it both ways: with the fix reverted, the new e2e test genuinely times out waiting for the success text (confirming the dialog really was blocking it); with the fix in, it passes.
- New unit tests for `_error_message`: a broken-input-probe-only failure returns `None` (not the probe's own error); a probe failure *alongside* a real failed action still correctly surfaces the real one.
- Full backend suite (216 tests, +5, including the new real-browser e2e test) passes.
- **Not yet completed:** the dialog fix is verified against a local fixture reproducing the pattern, not the live site itself, since this sandbox can't reach it - worth confirming on your next real Automation Exercise Contact Us run that the success message now actually appears.

---

## Same misattribution bug, one level broader: a resolved retry blamed for an unrelated failure

**Context:** A real `subscribe_to_newsletter` run showed "Click the subscribe button" as PASS (it took 4 attempts, but did succeed), yet the overall FAIL finding's error message was a truncated, unparseable JSON string from one of the earlier, already-resolved attempts - not the real reason. The Verifier had already written the correct explanation ("Newsletter subscription fails to show the success confirmation message"), but the misattributed error sat right next to it, undermining it.

**Prompt:** "this kinda reports should be test passed but heres the error at testing / dn say test hi fail hogaya" - i.e. don't just accept "the test failed," actually explain why a report showing passing steps still reads as broken.

**What was found:** the previous round's fix only excluded deliberate broken-input probes from `_error_message()`'s fallback - too narrow. The real, general rule: once `exploration.completed` is `True`, *every* step in the log succeeded, including ones that needed a retry - a failed attempt earlier in that step's history is resolved noise by definition, not a cause of anything. The old fallback picked "the last failed action's error" with no regard for whether that action's own step ultimately succeeded, so any transient hiccup along the way (an LLM timeout, a truncated JSON response, anything) could get shown as "the error" for a completely unrelated, real assertion failure discovered afterward.

**What was generated:**
- `backend/app/agents/reporter.py` - `_error_message()` now returns `None` whenever `exploration.completed` is `True` and there's no `retry_error`/`exploration.error` - the fallback to "last failed action's error" is reserved for when the exploration genuinely never completed (a real `ExplorerError` stopped it), which is the only case where that's actually diagnostic. The `is_broken_input_attempt` exclusion from the previous fix is kept for that narrower, still-real path.

**What was checked/modified before accepting:**
- The previous round's `test_error_message_still_reports_a_real_failed_action_alongside_a_probe` assumed a scenario (completed exploration with a genuinely unresolved failed action) that can't actually happen in practice - `_execute_step` either resolves a step or raises, setting `completed=False`. Replaced it with two tests matching real behavior: a resolved retry inside a completed exploration now correctly returns `None`; a genuinely incomplete exploration still correctly surfaces its last real failure.
- New test for the exact reported scenario: a step that needed a retry before succeeding, inside a completed exploration, no longer surfaces that retry's error.
- Full backend suite (217 tests, +2 net) passes.
- **Not yet completed:** the underlying JSON-truncation itself (this time in the `reasoning` field) still happens occasionally even at the higher token budget from the previous round - harmless now since the retry loop absorbs it and the step still completes, but worth another bump to `DECISION_MAX_TOKENS` if it keeps costing extra action attempts (this run took 14 model calls / ~$0.12 for a 4-step workflow, higher than it should need).

---

## A successful login immediately undone by a spurious "Log Out" click

**Context:** A real ParaBank login run on Llama (Ollama) showed all 4 steps PASS (100% action accuracy), yet the verdict was FAIL, HIGH, citing "click on text='Log Out'" - a selector never mentioned in the workflow's own steps at all.

**Prompt:** "no keep it here loo we passed all steps but test failed" (with the report).

**What was found:** a genuinely new failure class, not a repeat of the two reporting-attribution bugs from the last two rounds. `_execute_step`'s loop unconditionally calls the model again after every successful action until it says "done" - including after a click that actually navigated to a new page. The real sequence: the login click succeeded and landed on ParaBank's Accounts Overview page; the loop asked the model again anyway, handing it a snapshot of that *new* page's elements (which include a normal "Log Out" link); Llama treated that as something it still needed to click, undoing the login it had just completed. The workflow ended up back at the logged-out homepage - a real, self-inflicted failure, not misreporting.

**What was generated:**
- `backend/app/agents/explorer.py` - `_execute_step()` now ends a step immediately after a successful `click` action that changed the page's URL, without asking the model again. This is a deterministic check (compares the URL before and after the click), matching the same "don't trust a weaker model to reliably say 'done'" philosophy already used for the redundant-navigate and repeated-action cases earlier in this file.
- No frontend change needed: `ReportCard.tsx`'s "Failed step" line reads `reproduction_steps.at(-1)` from the real action log - since the erroneous extra click can no longer happen, that log never contains it, and the misleading display is fixed at the source instead of patched at the display layer.

**What was checked/modified before accepting:**
- New unit test reproducing the exact scenario: a successful click that changes the URL ends the step at one action, even when a second (wrong) decision is already queued and would otherwise be consumed - proving the loop actually stops, not just that the assertion happens to pass.
- The shared `_FakeBrowser` test fixture's bare `page = object()` had no `.url` - needed one (matching `_fake_snapshot`'s URL, so existing tests' behavior is unchanged) for the new check to even run without crashing every other click-based test.
- Full backend suite (218 tests, +1) passes, including the real-browser e2e login test, which exercises this exact code path for real (a click that navigates) and still passes.
- **Not yet completed:** scoped specifically to `click` actions, since `fill`/`select`/`press` steps essentially never cause navigation on their own - if a future workflow has a step needing multiple sequential clicks that each navigate, this would end the step after the first one; none of the current registered workflows are written that way, but worth knowing if one ever is.

---

## A step's PASS/FAIL status read from the wrong action - third instance of the same bug class

**Context:** A real ParaBank Transfer Funds run correctly reached `pass_with_issues` overall (LOW severity, accurate "completed and passed, 1 action needed a retry" summary) - but the per-step table showed step 7 ("Submit the transfer") as **FAIL**, with a truncated, unparseable-JSON string as its note, even though the transfer genuinely succeeded.

**Prompt:** "now again wtf is this" (with the report) - the confusion this time wasn't the overall verdict (that part was correct), it was one specific step row contradicting it.

**What was found:** the real sequence was: the submit click succeeded; the loop queried the model again because the confirmation hadn't rendered in that snapshot yet ("the page still shows the transfer form rather than a conf[irmation]" - visible in the model's own truncated reasoning); that second, redundant decision hit the same JSON-truncation issue as the last two rounds and got logged as a failed action; a third, unlogged decision then recognized "done." Both the frontend's `buildStepRows` (`ReportCard.tsx`) and the PDF's `_step_rows` (`pdf_report.py`) determined a step's status from `stepActions[-1]` - the *last* logged action - which picked the redundant failure over the real success that came before it. This is the same "trust the last logged item instead of the real outcome" bug as the last two rounds, just in a third location.

**What was generated:**
- `frontend/src/components/ReportCard.tsx`'s `buildStepRows` and `backend/app/pdf_report.py`'s `_step_rows` both now mark a step PASS if *any* of its actions succeeded, FAIL only if *all* of them did - matching what "step completed" actually means, rather than what its last attempt happened to be.

**What was checked/modified before accepting:**
- New tests in both places for the exact scenario: a step with a successful action followed by an unrelated failed one now reads PASS with the real action count, in both the on-screen card and the PDF generator, keeping them in agreement as intended from the original report redesign.
- Confirmed the existing "single failed action, no successes" test still correctly reads FAIL - the fix only changes behavior when a real success is mixed in with a later failure, not for a step that never actually succeeded.
- Full backend suite (219 tests, +1) and frontend suite (33 tests, +1) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed:** this is the third round fixing a "last logged item ≠ real outcome" bug in a different location (error_message, then error_message again more broadly, now step status) - all three traced back to the same underlying JSON-truncation issue still occasionally happening even at the current token budget. The framing bugs are now fixed everywhere they were found, but the truncation itself is still the thing generating the noise in the first place.

---

## A resolved LLM hiccup shouldn't demote a clean pass to pass_with_issues

**Context:** Direct pushback on the last several rounds' fixes: "cif any action btw 6-7 actions needed a retry doesnt mean test was passes with issues / retry shld made this declaration / fix it." A fair, sharper distinction than what the verdict logic actually made: `pass_with_issues` exists to surface a real hiccup *on the site being tested* (a slow-loading button, a flaky element) - genuine QA signal. But the failures chased over the last three rounds weren't that at all; they were Explorer's own LLM call failing to produce a usable decision (timeout, unparseable JSON, no text content) - a hiccup in our tooling, not evidence of anything wrong with the application under test. Counting that against the verdict conflated the two.

**What was generated:**
- `backend/app/agents/verifier.py` - `_count_errors()` now also excludes any action logged with `action == "unknown"`, on top of the existing broken-input-probe exclusion. "unknown" is Explorer's own convention for "no real action was ever attempted against the site" - it's set exactly and only in the `LLMError` catch block, when the model call itself failed before there was ever a decision to execute. A genuine site-side failure (a real Playwright timeout/error on an actual click, fill, etc.) still correctly counts - that distinction is what makes this a real fix rather than just hiding warnings.

**What was checked/modified before accepting:**
- New test: an `action="unknown"` failure (the exact LLM-hiccup shape) no longer demotes the verdict - `pass`, not `pass_with_issues`, `warning_count == 0`.
- Confirmed the existing `pass_with_issues` test (a real `action="fill"` Playwright failure - a genuine site-side flake) is untouched and still correctly demotes the verdict, proving the fix discriminates between the two rather than suppressing all warnings.
- Deliberately left the raw "Actions attempted / Pass rate" stats in the report unchanged - those are a technical execution-accuracy stat (fair to include every real attempt, hiccups included), distinct from the verdict, which is specifically a claim about the site's own behavior.
- Full backend suite (220 tests, +1) passes.
- **Not yet completed:** doesn't retroactively fix already-generated reports/history - this only changes verdicts for runs going forward from this fix.

---

## A real, silently-skipped required field - not another reporting artifact

**Context:** A real ParaBank Pay Bill run genuinely FAILED (HIGH severity): step 13, "Enter '12345' to verify account number," failed both of its attempts with "Claude's response contained no text content (cut off by max_tokens before any text was produced...)," and the exploration moved straight to steps 14-15 without that required field ever being filled - so ParaBank's own form validation correctly refused the payment and never showed "Bill Payment Complete." Pasted with no extra commentary.

**What was found:** unlike the last three rounds, this is not a misattribution bug - the reported failure is real and the site behaved correctly. The root issue is `DECISION_MAX_TOKENS` (600, from the very first round this phase) still being too tight for Claude under some prompts. The mechanism is worse than just "occasionally needs a retry": under a tight budget, a *short* decision (`{"action":"done",...}`) is far more likely to fit than a *longer* one (`{"action":"fill","selector":...,"value":...,"reasoning":...}`) - the JSON schema itself makes truncation asymmetric. So a truncation doesn't just cost a noisy retry; it can systematically bias the model toward claiming a step is already "done" instead of ever actually performing the fill. That's exactly consistent with step 13 being abandoned rather than eventually completed on retry.

**What was generated:**
- `backend/app/agents/explorer.py` - `DECISION_MAX_TOKENS` raised from 600 to 1200, with the comment updated to record the asymmetric-truncation theory and the real ParaBank evidence for it, so the reasoning survives the next person who's tempted to lower it back for cost reasons.

**What was checked/modified before accepting:**
- Grepped for any test hardcoding the old value - none found; this is a pure threshold change with no test fixture to update.
- Full backend suite (220 tests, no change) passes.
- **Not yet completed:** this is a budget increase, not a structural fix - the same failure mode is still theoretically possible at 1200 tokens for an unusually verbose response, just far less likely in practice. If it recurs, the next real fix would be more structural (e.g. a strict low-token retry that forces a minimal-field decision) rather than another round of raising the ceiling.

---

## Day 9 - Scheduled Testing & Simulated Failures

**Context:** The ticket's own acceptance criteria: a small subset of each domain's workflows run unattended on a fixed interval independent of any ticket, an on-demand dashboard trigger reuses the exact same execution path as the scheduled run, and - the part that actually matters - a step gets deliberately broken during development to prove detection works, not just claimed.

**Prompt:** "less apply ticket 9, 10 then will do try agaun / dont miss anth ok ?" with the Day 9 ticket text pasted (Day 10 wasn't pasted, so only Day 9 was scoped this round). The ticket's own acceptance criteria list is internally contradictory - it says "Each of the 6 domains" in one bullet and "Each of the 3 domains" in another, leftover from an earlier draft. The real registered count is 4 (`parabank`, `automation_exercise`, `practice_software_testing`, `campushub`) - applied to all 4, flagged the discrepancy to the user rather than guessing which stale number was intended.

**What was generated:**
- `backend/app/domains/schema.py` - `Workflow.smoke: bool = False`.
- All 4 domain YAMLs - 1-2 idempotent, side-effect-free workflows per domain flagged `smoke: true` (parabank: `login`, `find_transactions`; automation_exercise: `search_products`, `category_browse`; practice_software_testing: `login`, `search_no_results`; campushub: `student_login`, `view_own_records`). Deliberately avoided anything that registers a unique record or spends real money/state (e.g. `transfer_funds`, `open_new_account`) since these run unattended with nobody resetting state between cycles.
- `backend/app/agents/pipeline.py` - extracted `run_plan()` (Explorer -> Verifier -> Reporter for an already-built plan) out of `run_pipeline()`, which now just builds a plan via the Planner and hands it to `run_plan()`. This is what makes "the on-demand trigger reuses the same execution path as the scheduled run" literally true instead of two copies of the same logic that could drift - a scheduled/on-demand smoke run skips the Planner entirely (there's no Trello ticket behind it) and builds its `TestPlan` directly from the domain's own stored workflow, then calls the identical `run_plan()`.
- `backend/app/scheduler.py` (new) - `SmokeScheduler` wraps an `apscheduler.schedulers.asyncio.AsyncIOScheduler` job (`coalesce=True, max_instances=1` so a slow cycle never overlaps itself) that calls `run_cycle()` on a fixed interval (`SMOKE_INTERVAL_MINUTES` env, default 60) across every domain's smoke-flagged workflows in one tick. `run_now()` calls the exact same `run_cycle()`, just labeled `triggered_by="on_demand"` instead of `"scheduled"`. One workflow raising doesn't take the rest of the cycle down - caught, logged, and surfaced in the cycle's own `errors` list so a broken workflow is visible instead of silently dropped.
- `backend/app/main.py` - switched from the deprecated `@app.on_event` to a `lifespan` context manager that starts/stops the scheduler (`SKIP_SMOKE_SCHEDULER=1` env for tests/CI, so a unit test run never launches a real background Playwright job as a side effect); added `GET /api/scheduler/status` and `POST /api/scheduler/run-now`.
- `frontend/src/pages/Scheduler.tsx` + `.css` (new) - status panel (interval, next run, provider, smoke workflows grouped by domain, last cycle's pass/fail counts and any errors, links to each recorded run) plus the "Run Smoke Tests Now" on-demand trigger button; wired into `App.tsx`'s routes and `DashboardLayout.tsx`'s nav.
- `backend/requirements.txt` - added `apscheduler==3.11.3`.

**Deliberate failure - the actual evidence, not just a claim:**
- `backend/tests/e2e/fixtures/smoke_search_page.html` (new) - a minimal local fixture: a search box that shows "There are no results found for your search." for an unknown query.
- `backend/tests/e2e/fixtures/smoke_search_page_broken.html` (new) - the identical page with one line of real, deliberately injected regression: the "no results" branch writes an empty string instead of the message (see its own comment).
- `backend/tests/e2e/test_scheduler_real_browser.py` (new) - runs the real `SmokeScheduler.run_cycle()` (real `ExplorerAgent`, real `VerifierAgent`, real `ReporterAgent`, real `HistoryStore`, a real Playwright browser against a real local page; only the LLM transport is scripted via `FakeLLM`, same convention as the project's one other real-browser e2e test) twice: once against the correct fixture (asserts `pass_count == 1`), once against the broken one (asserts `fail_count == 1` and a real finding with the right summary).
- Captured live, once, outside the test itself, to have an actual artifact and not just a passing assertion:
  ```
  === SMOKE CYCLE RESULT (deliberately broken fixture) ===
  triggered_by: scheduled
  pass_count: 0 fail_count: 1
  domain/workflow: smoke_fixture_site search_no_results
  verdict: fail
  final_page_text: ' Search'
  finding severity: medium
  finding summary: Searching for a nonexistent product shows no message at all instead of a No results found notice.
  finding explanation: The result area never showed the expected no-results message - it stayed empty.
  ```
  Reverting the one-line regression and re-running the identical cycle correctly flips it back to `pass_count: 1, fail_count: 0` - the same two outcomes the checked-in test asserts, so this isn't a one-off manual observation, it's reproducible on demand.

**What was checked/modified before accepting:**
- `backend/tests/unit/test_scheduler.py` (new, 8 tests) - `list_smoke_workflows()` only returns flagged workflows; `_build_plan()` matches the domain's real stored workflow and rejects one that no longer exists; `run_cycle()` runs every smoke workflow across every domain and records to history; `run_now()` produces `triggered_by="on_demand"` through the identical `run_cycle()`; a fail verdict counts as failed; one workflow raising doesn't take the rest of the cycle down.
- `backend/tests/functional/test_scheduler_endpoints.py` (new, 4 tests) - both endpoints require auth; status only lists smoke-flagged workflows; run-now triggers a cycle (run_plan faked - a functional/API test shouldn't launch a real browser, that's what the e2e file above is for), updates `last_cycle`, and the run is genuinely queryable back through `/api/history/{id}`. Caught and fixed a real wiring gap while writing this: `smoke_scheduler` is a module-level singleton built once with the app's original `HistoryStore`, so the existing `app_history` fixture's rebinding of `main_module.history` for test isolation doesn't reach it on its own - pointed the scheduler's `_history` at the same isolated store explicitly.
- Full backend suite (234 tests, +12 net) passes; frontend `tsc --noEmit` and `vitest` (33 tests) pass.
- Confirmed no real network/API keys were required anywhere in this round's own tests - live automated site access from this environment is blocked by network policy, and no Claude/Trello/SMTP credentials are configured here, so the deliberate-failure evidence above had to be produced entirely against a local fixture with a scripted LLM. This wasn't a workaround chosen for convenience - it's the same limitation and the same solution (a local HTTP fixture server, FakeLLM-scripted decisions) already established and documented in an earlier round of this project for the confirm()-dialog fix, applied here at the scheduler level instead of the Explorer level.
- **Not yet completed:** Day 10 wasn't pasted this round, so it's untouched. The smoke interval (60 min default) and single-provider choice (`claude` default) are both configuration, not hardcoded - not yet exposed as an editable setting from the dashboard itself, only via env vars. `SmokeScheduler` doesn't yet retry a workflow that failed due to a genuine transient issue (e.g. the same LLM-hiccup class fixed earlier this session) before recording it - each smoke run gets exactly the same one-shot treatment a ticket-triggered run gets, nothing scheduler-specific.

---

## Trello Settings page - connecting Trello from the UI instead of a backend .env file

**Context:** A mentor review flagged a real onboarding gap: the app assumed Trello (`TRELLO_API_KEY`/`TRELLO_TOKEN`) was already configured via a backend `.env` file, with no way for a first-time or hosted, non-technical user to set it up from the UI at all. Discussed a few options over email (full per-user OAuth vs. a scoped-down version) - landed on the smaller, achievable-in-hours version: one shared connection, entered and saved from the dashboard, replacing the requirement to edit a config file on the server.

**Prompt:** the finalized plan from the mentor email exchange, then "less apply this / do this e2e / dn miss anth."

**What was generated:**
- `backend/app/trello_settings.py` (new) - `load_trello_settings()` / `save_trello_settings()` / `clear_trello_settings()`, reading/writing a small local JSON file, deliberately the same lightweight file-storage pattern the domain manifest (`app/domains/manifest.py`) already uses - except this one lives under the already-gitignored `backend/data/` (matching where `history.db` lives), never `app/domains/data/`, since this file holds real secrets, not shareable domain knowledge.
- `backend/app/mcp_server/trello_client.py` - `TrelloClient.__init__` now prefers stored settings over `TRELLO_API_KEY`/`TRELLO_TOKEN` env vars, falling back to the env vars unchanged if nothing's been saved from the dashboard - so an existing `.env`-based setup (like the one already running locally) keeps working with zero changes.
- `backend/app/main.py` - three new endpoints: `GET /api/trello/status` (connected + which source: `"settings"` | `"env"` | `"none"` - never the key/token themselves, so a saved secret never round-trips back to the browser), `POST /api/trello/settings` (save, rejects empty fields), `DELETE /api/trello/settings` (disconnect - falls back to env vars afterward if those are still set, same as if nothing had ever been saved).
- `frontend/src/pages/TrelloSettings.tsx` + `.css` (new) - mirrors `DomainKnowledge.tsx`'s exact shape (form panel + status panel) for speed and consistency: API key/token fields, a direct link to Trello's own key/token page, a status card showing which source is active, and a Disconnect button shown only when the connection came from the dashboard itself (nothing to disconnect if it's env-based). Added to the sidebar directly below "Domain Knowledge," per the agreed plan, and its own route.
- `frontend/src/services/api.ts` - added `apiDelete()`, the one HTTP verb the existing helpers didn't cover yet.

**What was checked/modified before accepting:**
- `tests/unit/test_trello_settings.py` (new, 7 tests) - round-trip save/load, missing file, malformed JSON, a field missing, disconnect clears it, disconnecting when nothing was ever saved is a safe no-op.
- `tests/functional/test_trello_settings_endpoints.py` (new, 11 tests) - all three endpoints require auth; empty fields rejected; save-then-status reflects `"settings"`; **the save response body never contains the raw secret text** (checked directly against the response text, not just the schema); disconnect clears the connection and correctly falls back to `"env"` if env vars are still set underneath it; settings source takes precedence over env when both exist.
- Existing `test_trello_client.py` suite (7 tests) still passes completely unchanged - confirms the precedence logic is genuinely backward compatible for the current `.env`-based setup, not just in theory.
- `frontend/src/tests/TrelloSettings.test.tsx` (new, 6 tests) - not-connected/settings/env status states render correctly, Disconnect only appears for the settings source, empty-field submission is rejected client-side without an API call, save and disconnect both trigger a real reload of status afterward.
- Full backend suite (279 tests, +18) and frontend suite (47 tests, +6) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed, and explicitly flagged to the mentor already:** this is one shared connection, not per-user (the app has a single shared login, not real user accounts, so there's no way to have two people's Trello boards connected at once); disconnecting deletes the local file but doesn't revoke the token on Trello's own side (only the user's own Trello account settings can do that); still requires manually generating a key/token from Trello's site rather than a one-click OAuth "Sign in with Trello" flow. All three are documented, agreed-on tradeoffs for this scope, not oversights.

---

## Day 10 - Ask-the-Site Search Bar & On-Demand Queries

**Context:** The ticket's own framing: a search bar that answers plain-English questions about a known domain at any time - before, during, or after a run - by reusing the Explorer in an on-demand mode "rather than introducing a separate agent," and an unrecognized-domain query must decline the same way a test run does, never guess.

**Prompt:** "ig its alr done" (Day 9), then the Day 10 ticket pasted with "1. Add epic / 2. KAN-16" Jira metadata and `Branch: feature/search-bar`. Confirmed the branch choice with the user the same way as Day 9's (new branch matching the ticket's own field, off the current work).

**What was found:** the codebase already had half of the "richer context" answer path in a different shape - `/api/history/{run_id}/ask` answers a question about one *finished, saved* run from its stored report. Day 10 needed something broader: a domain-scoped question independent of any specific run, with a *live* browsing fallback when there's no relevant run to answer from - which is what actually justifies "reuses the Explorer" instead of just another LLM-over-stored-data endpoint like the existing one.

**What was generated:**
- `backend/app/agents/schema.py` - `AskContext` (whatever richer context a caller already has: domain, final_url/final_page_text, actions) and `AskResult` (question, matched, domain/reason, answer, source, final_url, actions).
- `backend/app/agents/explorer.py` - `ExplorerAgent.ask(question, existing_context=None, close_browser=True)`, entirely on the existing agent, no new agent class:
  - `_match_domain_for_question()` - the same "decide which registered domain this concerns, or say it doesn't match - never guess" prompt shape as the Planner's own `_match_domain`, adapted from a ticket to a free-form question. A hallucinated domain name outside the real manifest is treated as unmatched, same principle as the Planner already applies.
  - `_answer_from_context()` - answers directly from an `AskContext` with one LLM call, no browser - the "during/after a run" fast path.
  - `_ask_live()` - a new, small bounded loop (`ASK_MAX_ACTIONS = 4`, on purpose much smaller than a workflow step's budget - a question should only ever need a couple of clicks, not a multi-step workflow) reusing `_snapshot`/`_resolve_selector`/`_execute_action`/`_emit_action`/`_live_frame_loop` - the same real browsing machinery `explore()` uses - with a new `_ask_prompt()` that lets the model either take one more browsing action or answer now. Falls back to `_answer_from_context()` on whatever was actually observed if the budget runs out without a direct answer, rather than failing the question outright.
- `backend/app/main.py` - new `/ws/ask-site` WebSocket (auth via the same `require_auth_ws` as `/ws/pipeline`): client sends `{"question", "provider", "context"}` once, server streams live action events while browsing (identical event shape to `/ws/pipeline`'s), then exactly one terminal event - `declined` or `answer`. A malformed `context` payload is ignored (falls back to live exploration) rather than failing the request.
- `frontend/src/hooks/usePipelineRun.ts` - two small additions so a live/finished run's context is actually available to ask from: `actionsLog` (every real action for the run's lifetime, unlike `frameHistory`'s 10-frame cap for the filmstrip) and `baseUrls` (the domain's `base_url` captured off the Explorer's first `"page_loaded"` action) - lets the search bar resolve which registered domain a still-*running* provider is on, without waiting for `pipeline_done`.
- `frontend/src/hooks/useAskSite.ts`, `frontend/src/types/asksite.ts`, `frontend/src/components/AskSiteBar.tsx` + `.css` (all new) - a fresh WebSocket per question; the bar reads `usePipelineRunContext()` and, if a run has finished for a matching domain, sends its real `exploration` as context; if a run is still going, sends the actions observed so far (domain resolved via `baseUrls` against `/api/domains`); otherwise sends no context, which correctly triggers a live check. Mounted once in `DashboardLayout`'s topbar, so it's present on every route regardless of run state - satisfying "available on the dashboard at all times" directly rather than duplicating it per page.

**What was checked/modified before accepting:**
- `backend/tests/unit/test_explorer_ask.py` (new, 7 tests) - declines an unrecognized domain without ever touching the browser; declines a hallucinated out-of-manifest domain; answers from existing context without browsing when the domain matches; ignores existing context for a *different* domain (falls through to live); answers immediately when the first page is enough; browses one action before answering; falls back to a context-answer when the action budget runs out.
- `backend/tests/functional/test_ws_ask_site.py` (new, 7 tests) - auth required; empty question and unknown provider rejected; decline path; live action events stream before the final answer event; the provided context is actually threaded through to `ExplorerAgent.ask()`; a malformed context is ignored, not fatal.
- `backend/tests/e2e/test_ask_site_real_browser.py` (new, 4 tests) - the actual acceptance criterion: real `ExplorerAgent.ask()`, a real Playwright browser, two real local fixture domains (reusing `login_page.html` and Day 9's `smoke_search_page.html`), three distinct query types - a direct factual question answered from the first page with zero browsing actions, a single-action behavior probe (search for a nonexistent product), a multi-action negative probe (wrong login credentials) on the *other* domain - plus one decline case for a domain that isn't registered at all. Captured live, once, outside the tests themselves as evidence the answers are genuinely observed, not scripted results dressed up as proof:
  ```
  === Type 2: single-action behavior probe (fixture_shop) ===
  question: What does the site show when you search for a product that doesn't exist?
  matched: True | domain: fixture_shop
  actions taken: [('fill', '#search'), ('click', '#search-btn')]
  answer: Searching for a nonexistent product shows the message There are no results found for your search.

  === Type 3: multi-action negative probe (fixture_login_site)
  question: What happens if you try to log in with the wrong username and password?
  matched: True | domain: fixture_login_site
  actions taken: [('fill', '#username'), ('fill', '#password'), ('click', '#login-btn')]
  answer: Logging in with the wrong username and password does not show the welcome message - the login form stays on screen with no visible error.
  ```
- `frontend/src/tests/AskSiteBar.test.tsx` (new, 4 tests) - the search bar renders regardless of run state; a decline shows the "no domain knowledge" message, not a guess; a matched answer shows its domain badge; a just-finished run's real `exploration` data is genuinely what gets sent as `context` for a matching follow-up question (asserted against the exact JSON payload sent over the fake WebSocket, not just that *something* was sent).
- Full backend suite (252 tests, +18 net) passes; frontend `tsc --noEmit`, `oxlint`, and `vitest` (37 tests, +4) all pass.
- **Not yet completed:** the "during a run" context path resolves the active provider by picking whichever of claude/ollama has a result or base_url first - genuinely ambiguous for a "both" comparison run (which of the two providers' in-progress context should a question use?), not something this round tried to resolve properly. The search bar also always asks on the `claude` provider regardless of which model a run used - no provider picker on the bar itself yet.

---

## A parenless XPath-text selector variant slipped past the existing fix

**Context:** A real ParaBank transfer_funds run on Groq-hosted Llama genuinely failed: step 5 ("Open the Transfer Funds page from Account Services") timed out and hit the loop guard after 3 identical attempts on `a[text='Transfer Funds']` - HIGH severity, correctly stopped the run, but the underlying cause was a bug, not the model being wrong about what to click.

**Prompt:** pasted the report card, "llama is again nt working in testing wtf."

**What was found:** an existing fix (way earlier this project) already handles the model writing XPath-style text matches instead of real CSS - `a[text()='Dropdown']` gets rewritten to Playwright's `text="Dropdown"`. This run's selector, `a[text='Transfer Funds']`, is a *different* malformed shape - no parens after `text` at all - which `_XPATH_TEXT_PATTERN`'s regex (`text\(\)\s*=...`, parens mandatory) never matched, so it fell straight through to Playwright unresolved and timed out against valid-looking-but-meaningless CSS, on a link that was genuinely present on the page. First attempt at broadening the regex to `text\(\)?\s*=...` still silently failed the exact real case - `\(\)?` only makes the *closing* paren optional while still requiring the opening one, not the "()" pair together; caught by testing the fix directly against the real failing string before accepting it, not just re-running the existing test suite (which wouldn't have caught this, since the old cases still passed).

**What was generated:** `backend/app/agents/explorer.py` - `_XPATH_TEXT_PATTERN` corrected to `text(?:\(\))?\s*=\s*['"]([^'"]+)['"]` (the `()` grouped together as one optional unit), so both `text()='X'` and `text='X'` now resolve to `text="X"`.

**What was checked/modified before accepting:**
- Verified directly against both real strings (`a[text='Transfer Funds']` and `a[text()='Dropdown']`) via `ExplorerAgent._resolve_selector()` before touching any test file - this is what caught the first, wrong fix attempt.
- New test `test_resolve_selector_normalizes_parenless_text_attribute_pattern`, reproducing the exact real ParaBank selector.
- Full backend suite (253 tests, +1) passes.
- **Not yet completed:** can't re-run the exact real ParaBank ticket against the user's own Groq setup from this sandbox (network egress blocked, no Groq key here) - the fix is verified at the selector-resolution level directly against the real failing string, not via a fresh end-to-end run against the live site.

---

## The "Ask anything" chatbot couldn't say why a test failed

**Context:** A screenshot showed the dashboard's global chat widget asked "check what the reason llama failed," replying that it didn't have the report contents in front of it and would have to invent an answer - the day-10 `/ws/ask-site` search bar answers grounded questions about a *site*, but this separate, older, general-purpose chat (the "Ask anything" box, `/api/chat`) had no access to run history at all - its prompt only ever contained static architecture facts (registered domains/workflows), never anything about what actually happened in a real run.

**Prompt:** "this shld be fixed too / this chatbot shld tell why test failed, could be one line straight forward anserbut shld tell" (with the screenshot).

**What was generated:** `backend/app/main.py` - new `_recent_runs_context()` pulls the last 5 recorded runs (`history.list_runs()` + `history.get_run()` for each) and formats each one's real verdict, the Verifier's actual explanation, and every finding's real summary/error message into a compact block, injected into `/api/chat`'s prompt right alongside the existing static system facts. The prompt now explicitly tells the model to answer "why did that fail/pass" directly and specifically from this real data - assuming the most recently listed run when the question doesn't name one - instead of declining, and to only say it doesn't know when the real data genuinely doesn't cover the question (never invent).

**What was checked/modified before accepting:**
- New test reproducing the exact real complaint: records a real `PipelineResult` matching the screenshot's actual ParaBank ticket (`QnhoyKRV`, transfer_funds, the same "stopping to avoid a loop" finding and Verifier explanation from the earlier selector-fix report), asks "its done, now check what the reason llama failed" through `/api/chat`, and asserts the captured prompt actually contains the ticket id, the real finding text, and the Verifier's own explanation - not just that *some* context was added.
- Confirmed the existing chat tests (grounded-in-real-domains, conversation history, run-ticket intent detection) still pass unchanged - the new context is additive to the prompt, not a replacement for anything already there.
- Full backend suite (254 tests, +1) passes.
- **Not yet completed:** capped at the last 5 runs and doesn't try to disambiguate which run the user means beyond "assume the most recent one" - a question about an older or specifically-named run several runs back could still miss if it's fallen out of that window. Same live-verification limitation as the selector fix above (no real Groq/Claude key in this sandbox to confirm the model's actual reply reads naturally, only that the real data reaches its prompt).

---

## The redundant-first-step skip silently ate the wrong page for Toolshop's login

**Context:** A Practice Software Testing (Toolshop) login report showed a HIGH finding - "Login fails to authenticate... blocking access to the core login workflow" - despite every step showing PASS. Asked to fix "if all steps have passed why fail result." While investigating, a re-run surfaced the real smoking gun: "claude isnt filling email bar, just filling pw and loging in" - the email step wasn't even being attempted anymore, on a fresh run.

**Prompt:** "this is what u need to fix / if all steps have passed why fail result" then, mid-fix, "no i reran, claude isnt filling email bar / just filling pw and loging in."

**What was found:** the real root cause, once the second report changed what needed explaining. An earlier optimization (this project's own "Skipping a redundant first-step LLM call" round, built for ParaBank's "Navigate to the ParaBank homepage" step) skips a workflow's first step entirely, with no model call at all, whenever it's non-interactive AND the browser is already at `domain.base_url` right after the initial `goto()`. That check never verified the step actually *wants* `domain.base_url` - it just assumed a non-interactive first step always means "be on the homepage." Toolshop's login workflow's first step is "Navigate to the URL `https://practicesoftwaretesting.com/auth/login` (a direct page navigation...)" - a *different* page than `domain.base_url` (the plain homepage). The skip fired anyway, so the Explorer never actually navigated to the login page at all - it silently stayed on the homepage, and every step after that (fill email, fill password, click login) ran against the wrong page the whole time. That explains both symptoms: sometimes the model found *something* on the homepage it decided looked like an "Email field" and filled it (the first report); other times it correctly found none and skipped straight to whatever it could find for password/login (the second, live-observed run). Neither run was ever actually testing the login page.

**What was generated:**
- `backend/app/agents/explorer.py` - `_LITERAL_URL_PATTERN` (new) extracts a literal URL from a step's own text, if it names one. The skip check now compares the browser's current URL against *that* literal URL when the step has one, falling back to `domain.base_url` only when it doesn't (preserving the original ParaBank case, which never names a literal URL). A first step naming a different page than `domain.base_url` no longer gets treated as already-satisfied.
- `backend/app/pdf_report.py` and `frontend/src/components/ReportCard.tsx` - separately, `_step_rows()`/`buildStepRows()` now mark the *last real action* FAIL (not PASS) when the workflow completed but the overall verdict is still "fail" - every earlier step genuinely achieved its own local goal, but the terminal step whose success the final assertion actually depends on shouldn't read as a clean, unqualified PASS sitting directly above a FAIL badge. This part stays useful as general report-clarity even now that the real underlying cause is fixed - a genuine "click succeeded, but the site didn't do what was expected" case can still happen for other reasons.

**What was checked/modified before accepting:**
- New Explorer tests: a first step naming a literal URL different from `domain.base_url` is no longer skipped (goes through the real decision loop, which is what actually navigates there); the original ParaBank-style first step with no literal URL still gets skipped exactly as before - the fix doesn't regress the case it was built for.
- New `_step_rows`/`buildStepRows` tests: every action succeeding with an overall "fail" verdict downgrades only the last step to FAIL, both earlier steps stay PASS; a `pass_with_issues` verdict (where the real assertion WAS satisfied) leaves every step alone.
- Full backend suite (258 tests, +4) and frontend suite (38 tests, +1) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed:** can't re-run the exact real Toolshop ticket against the live site from this sandbox to confirm login now actually reaches `/account` - the fix is verified at the skip-condition level directly (a first step with a differing literal URL is no longer silently treated as satisfied), not via a fresh end-to-end run against the real page. Worth a real re-run to confirm before relying on it for the demo.

---

## A fill that "succeeded" but the field was empty by click time

**Context:** The navigation fix above worked - both providers' live views confirmed reaching the real `/auth/login` page - but Claude's login still failed to authenticate, and the live screenshot showed why: "Email is required" in red, right at the moment Login was clicked, despite the report showing the email step "Completed successfully in 2 action(s)." Re-ran it once to rule out one-off model variance - identical failure both times, same "2 action(s)" both runs. A deterministic repeat, not noise.

**Prompt:** "re ran it, same email error again."

**What was found:** `_execute_action`'s `fill` branch only ever checked whether Playwright's `page.fill()` call itself raised - it never checked whether the value was still there afterward. A JS-heavy form (client-side validation, a re-render clearing the field, a stale element reference from a snapshot taken just before one) can silently reset a field with no exception at all - `fill()` genuinely succeeds, Playwright has no way to know the page then undid it. Given the deterministic 2-repeat and the exact symptom (empty field, required-validation showing, right at submit time), this fully explains the mystery: the Explorer believed the field was filled because nothing ever threw, while the real page disagreed.

**What was generated:** `backend/app/agents/explorer.py`'s `_execute_action()` now reads the field back (`page.locator(selector).input_value()`) immediately after every `fill`, and treats a value that doesn't match what was set as a real failure - not the `fill()` call throwing, but the *result* being wrong - with a message naming the selector and what it actually shows now, so the model sees this happened and can retry (or the report can honestly show it as a failure) instead of the action log claiming a clean success while the real field silently isn't there.

**What was checked/modified before accepting:**
- New fixture `tests/e2e/fixtures/self_clearing_field.html` - a real input whose own JS clears itself synchronously on every `input` event, reproducing the "fill succeeds, page undoes it" shape without depending on the live Toolshop site (unreachable from this sandbox) to prove it.
- New real-browser e2e test (`test_real_browser_catches_a_fill_that_silently_gets_cleared`) - drives a real `BrowserSession`/`ExplorerAgent._execute_action()` against that fixture and confirms the fill is now correctly reported as failed, with a message naming the selector.
- Full backend suite (259 tests, +1) passes, including the existing real-browser e2e tests (login/dialog fixtures) exercising the same new read-back code path with a normal, non-clearing field, confirming it doesn't false-positive on an ordinary successful fill.
- **Not yet completed:** the exact reason the real Toolshop field cleared itself (framework re-render vs. probe interaction vs. something else) is still unconfirmed - this fix makes the *symptom* (a fill that doesn't stick) visible and retryable regardless of cause, rather than depending on first diagnosing which of several plausible real-site causes it actually was. Worth a real re-run to confirm the retry now recovers cleanly rather than just failing faster with a clearer message.

---

## "FAIL" reads as the AI failing, not as a real finding

**Context:** A genuinely correct AutomationExercise newsletter-signup report - every action succeeded (75% action accuracy, no errors), the agent correctly detected the site never showed its own success confirmation - still read as a plain "FAIL" badge. Direct pushback: "that fail label is decreasing our testing rate, our validity and everything... it should not say the test has been failed... say passed, but the website is not showing that."

**What was decided, and why the literal ask was declined:** relabeling this as "passed" would mean the tool lying about a real result - the whole point of an AI QA agent is catching exactly this kind of regression, and every reporting fix this project has gone through this session exists specifically to make sure a "fail" verdict at this point in the pipeline means a genuine, confirmed site defect, not a tool-side hiccup. Explained this directly rather than complying, and offered the honest alternative that actually solves the real underlying problem (looking like the AI failed, not "the result is wrong"): keep the verdict data/logic exactly as-is, but change what it's *called* on screen so nobody reads a correct finding as the tool being broken. Confirmed the wording via `AskUserQuestion` - "ISSUE FOUND" (recommended) over "BUG DETECTED" or leaving "FAIL" with added subtext.

**What was generated:**
- `frontend/src/utils/verdict.ts` (new) - `verdictLabel()`, a single shared function turning a raw verdict string into its display label - `"fail"` reads as `"ISSUE FOUND"`, everything else unchanged. Applied everywhere a verdict gets shown as text: `ReportCard.tsx`'s header badge, `History.tsx`'s and `Dashboard.tsx`'s status columns, `ComparisonSummary.tsx`'s verdict row.
- `backend/app/pdf_report.py` - matching `_verdict_label()`, applied to both the PDF's "Overall result" and "Result" rows.
- `backend/app/agents/reporter.py` - `_render_summary()`'s "Result: ..." line (the one posted straight to Trello, the most externally-visible artifact of all) now reads "ISSUE FOUND" too, for the same reason.
- Deliberately scoped to the *overall verdict* label only - per-step status cells ("FAIL" on a specific action) and CSS class names (`report-badge-fail`, `history-status-fail`, etc.) are untouched. A step-level FAIL means something different (this specific action didn't execute cleanly) from the overall verdict (the site's real behavior didn't match what was expected) - conflating the two into one relabeling would blur a distinction this project has spent several rounds this session establishing.

**What was checked/modified before accepting:**
- Updated the existing "FAIL badge" tests in `ReportCard.test.tsx` and `test_reporter.py` to assert the new label - re-read each one first to confirm none were actually testing verdict *logic* (only display text), so no behavior was silently changed alongside the wording.
- New tests: `verdict.test.ts` (frontend) and `test_verdict_label_*` (backend `pdf_report`) directly cover the label mapping in isolation.
- Full backend suite (261 tests, +2) and frontend suite (41 tests, +3) pass; `tsc --noEmit` and `oxlint` clean.
- **Not yet completed:** the AI-written PDF narrative (Claude's own prose summary/analysis section) still describes the raw verdict word ("fail") in its own generation prompt - the visible badges/labels are now consistent, but Claude's free-form narrative text itself wasn't specifically instructed to avoid saying "the test failed" in its own words. Worth revisiting if a generated narrative reads inconsistently with the badge above it.

---

## Renaming the project from "SentinelQA" to "ProTester"

**Context:** the mentor flagged that "SentinelQA" collides with an existing, already-published QA product name and needs to change before the project ships further. Asked for name suggestions with one explicit, load-bearing constraint: **"change name make sure whatever name u usggest its nt alr present"** - every candidate had to be actually verified as not already in use, not just plausible-sounding. Checked each candidate live via web search before presenting it; several were caught and dropped as already taken (QAgent, ScoutQA, QAman, Verifai, Testronaut, Siteproof) before they could repeat the exact "SentinelQA already exists" mistake. Final decision: **"no go with ProTester."**

**What was generated:** every literal `"SentinelQA"` occurrence in the tracked codebase replaced with `"ProTester"` - the browser tab title (`frontend/index.html`), the sidebar brand name (`DashboardLayout.tsx`), the login page brand name (`LoginPage.tsx`), the empty-state copy in the global chat (`GlobalChat.tsx`), a CSS comment (`index.css`), the Playwright e2e suite's `test.describe` name (`dashboard.spec.ts`), the FastAPI app title and the `/api/chat` system prompt's opening line (`backend/app/main.py`), and the PDF report's title `Paragraph` (`backend/app/pdf_report.py`). Also updated `README.md`'s H1 from the generic "Agentic Web QA Tester" to the actual product name, since the mentor's checklist explicitly called for the new name to be reflected "throughout the project, README, and presentation."

**What was checked/modified before accepting:**
- Grepped the full repo for `SentinelQA` before starting (8 files, 10 occurrences) and again after every file was edited, confirming zero occurrences remain anywhere in the tracked codebase.
- Searched both `backend/tests` and `frontend/src` for any hardcoded brand-name string assertions that a pure text rename could silently break - none found, so no test files needed changes.
- Full backend suite: 270 of 279 pass; the 9 failures are pre-existing real-browser e2e tests (`test_ask_site_real_browser.py`, `test_explorer_real_browser.py`, `test_scheduler_real_browser.py`) failing on a missing Playwright browser executable in this environment - unrelated to the rename, which touched only string literals, no logic.
- Full frontend suite: `tsc --noEmit` clean, `oxlint` clean (only two pre-existing, unrelated fast-refresh warnings), `vitest run` 47/47 passing.
