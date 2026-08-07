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
