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
