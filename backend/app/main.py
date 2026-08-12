"""Day 1 scaffolded the pipeline with mock data. Day 2 added a real browser
driver behind a WebSocket for one-off page loads. /ws/pipeline is the real
thing: it drives the full Planner -> Explorer -> Verifier -> Reporter
pipeline against a Trello ticket, with a model choice (Claude, Ollama, or
both side by side), streaming each agent's status live instead of returning
one final blob.
"""

import json
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

if sys.platform == "win32":
    # The default SelectorEventLoop on Windows can't launch subprocesses
    # (NotImplementedError from asyncio's _make_subprocess_transport) -
    # Playwright launches its browser driver as a subprocess, so every
    # browser.start() call hangs forever with no error on this loop.
    # ProactorEventLoop is the one Windows policy that supports it, and
    # this must run before anything else creates the event loop.
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.claude_client import ClaudeLLMClient
from app.agents.llm_client import LLMError
from app.agents.pipeline import make_llm, run_both, run_pipeline
from app.auth import AuthError, login as auth_login, logout as auth_logout, require_auth, require_auth_ws
from app.browser import BrowserSession
from app.domains.manifest import load_domains, save_workflow, slugify
from app.domains.schema import Domain, ExpectedOutcome, Workflow
from app.history.schema import (
    ComparisonHistoryEntry,
    DailyStat,
    HistoryDetail,
    HistoryEntry,
    HistoryStats,
    ProviderStats,
    SiteStats,
)
from app.history.store import HistoryStore
from app.mcp_server.trello_client import TrelloError, verify_trello_credentials
from app.pdf_report import generate_report_pdf
from app.scheduler import SmokeScheduler, list_smoke_workflows
from app.trello_settings import clear_trello_settings, load_trello_settings, save_trello_settings

load_dotenv()

history = HistoryStore()
smoke_scheduler = SmokeScheduler(history=history)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # SKIP_SMOKE_SCHEDULER exists for tests/CI - a scheduled job launching
    # real Playwright browsers against real sites every interval is the
    # last thing a unit test run should trigger as a side effect.
    if os.environ.get("SKIP_SMOKE_SCHEDULER", "").lower() not in ("1", "true"):
        smoke_scheduler.start()
    yield
    smoke_scheduler.shutdown()


app = FastAPI(title="ProTester", lifespan=_lifespan)

# Comma-separated real origins (e.g. a deployed Vercel/Netlify frontend
# URL) can be added via ALLOWED_ORIGINS without touching this file -
# localhost:5173 stays allowed by default so local dev keeps working
# unchanged whether or not the env var is set.
_extra_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", *_extra_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Live-run and report screenshots (explorer.py's per-action captures,
# verifier.py's failure captures) - reports/ is gitignored, so a fresh
# checkout won't have this directory yet; StaticFiles requires it to exist
# up front.
SCREENSHOTS_DIR = "reports/screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


@app.post("/api/auth/login", response_model=LoginResponse)
def api_login(body: LoginRequest) -> LoginResponse:
    try:
        token = auth_login(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return LoginResponse(token=token, username=body.username)


@app.post("/api/auth/logout")
def api_logout(token: str = Depends(require_auth)) -> dict:
    auth_logout(token)
    return {"status": "ok"}


@app.get("/api/auth/me")
def api_me(token: str = Depends(require_auth)) -> dict:
    return {"authenticated": True}


class TestRunResult(BaseModel):
    status: str
    pages_visited: int
    actions_taken: int
    bugs_found: int
    summary: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/mock-run", response_model=TestRunResult)
def mock_run() -> TestRunResult:
    """Stands in for a real test run until the Explorer/Verifier/Reporter
    agents exist (Days 4-8). Returns a fixed, fake result so the frontend
    has something real to fetch and render end to end."""
    return TestRunResult(
        status="complete",
        pages_visited=3,
        actions_taken=7,
        bugs_found=1,
        summary=(
            "Mock run - no real agent yet. Visited 3 pages, tried 7 actions, "
            "found 1 fake bug: 'Login button unresponsive on mobile viewport.'"
        ),
    )


@app.websocket("/ws/run")
async def run_live_test(websocket: WebSocket) -> None:
    """Drives a real browser to the given URL, streaming status updates to
    the client as each step happens instead of waiting for one final result.
    """
    await websocket.accept()
    session = BrowserSession()
    try:
        data = await websocket.receive_json()
        url = data.get("url")
        if not url:
            await websocket.send_json({"type": "error", "message": "No URL provided."})
            return

        await websocket.send_json({"type": "status", "message": "Launching browser..."})
        await session.start()

        await websocket.send_json({"type": "status", "message": f"Navigating to {url}..."})
        title = await session.goto(url)

        await websocket.send_json(
            {
                "type": "done",
                "url": url,
                "title": title,
                "message": f'Loaded page. Title: "{title}"',
            }
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        await session.close()


VALID_MODELS = ("claude", "ollama", "both")


@app.websocket("/ws/pipeline")
async def run_pipeline_ws(websocket: WebSocket, token: str = Depends(require_auth_ws)) -> None:
    """Client sends {"ticket_id": "...", "model": "claude"|"ollama"|"both"}
    once, then receives a stream of stage_start/stage_end/stage_error events
    as the pipeline runs (plus one "action" event per Explorer browser
    action - a screenshot_url/target_box/viewport for a live view), followed
    by one pipeline_done per provider and (for "both") one comparison_done.
    Connect as /ws/pipeline?token=<token>
    from login - the WebSocket API can't set an Authorization header."""
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        ticket_id = data.get("ticket_id")
        model = data.get("model", "claude")

        if not ticket_id:
            await websocket.send_json({"type": "error", "message": "No ticket_id provided."})
            return
        if model not in VALID_MODELS:
            await websocket.send_json(
                {"type": "error", "message": f"Unknown model {model!r} - expected claude, ollama, or both."}
            )
            return
        if not _trello_status().connected:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": "Trello isn't connected yet - every ticket run reads its details from Trello, "
                    "so connect it from Trello Settings first.",
                }
            )
            return

        async def on_event(event: dict) -> None:
            await websocket.send_json(event)

        if model == "both":
            claude_result, ollama_result, comparison = await run_both(ticket_id, on_event=on_event)
            # Either side can come back None if it failed - run_both already
            # let it fail on its own terms (with a real stage_error) instead
            # of dragging the other side down with it. Only pair them under
            # one comparison_group, and only build a comparison, when both
            # actually succeeded.
            comparison_group = history.new_comparison_group() if (claude_result and ollama_result) else None

            if claude_result is not None:
                claude_id = await history.record_run(claude_result, comparison_group)
                await websocket.send_json(
                    {
                        "type": "pipeline_done",
                        "provider": "claude",
                        "history_id": claude_id,
                        "result": claude_result.model_dump(mode="json"),
                    }
                )
            if ollama_result is not None:
                ollama_id = await history.record_run(ollama_result, comparison_group)
                await websocket.send_json(
                    {
                        "type": "pipeline_done",
                        "provider": "ollama",
                        "history_id": ollama_id,
                        "result": ollama_result.model_dump(mode="json"),
                    }
                )

            if comparison is not None and comparison_group is not None:
                await history.record_comparison(comparison, comparison_group)
                await websocket.send_json(
                    {
                        "type": "comparison_done",
                        "comparison_group": comparison_group,
                        "comparison": comparison.model_dump(mode="json"),
                    }
                )
            elif claude_result is None or ollama_result is None:
                failed = "claude" if claude_result is None else "ollama"
                await websocket.send_json(
                    {
                        "type": "error",
                        "provider": failed,
                        "message": f"The {failed} run failed - see the timeline above for why. No comparison available.",
                    }
                )
        else:
            result = await run_pipeline(ticket_id, model, on_event=on_event)
            run_id = await history.record_run(result)
            await websocket.send_json(
                {"type": "pipeline_done", "provider": model, "history_id": run_id, "result": result.model_dump(mode="json")}
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})


@app.get("/api/history", response_model=list[HistoryEntry])
async def list_history(
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
    provider: str | None = None,
    domain: str | None = None,
    _token: str = Depends(require_auth),
) -> list[HistoryEntry]:
    return await history.list_runs(limit=limit, offset=offset, search=search, provider=provider, domain=domain)


@app.get("/api/history/stats", response_model=HistoryStats)
async def history_stats(_token: str = Depends(require_auth)) -> HistoryStats:
    return await history.stats()


@app.get("/api/history/comparisons/{comparison_group}", response_model=ComparisonHistoryEntry)
async def get_comparison(comparison_group: str, _token: str = Depends(require_auth)) -> ComparisonHistoryEntry:
    entry = await history.get_comparison(comparison_group)
    if entry is None:
        raise HTTPException(status_code=404, detail="Comparison not found.")
    return entry


@app.get("/api/history/provider-stats", response_model=list[ProviderStats])
async def provider_stats(_token: str = Depends(require_auth)) -> list[ProviderStats]:
    return await history.provider_stats()


@app.get("/api/history/daily", response_model=list[DailyStat])
async def daily_stats(days: int = 7, _token: str = Depends(require_auth)) -> list[DailyStat]:
    return await history.daily_stats(days=days)


@app.get("/api/history/site-stats", response_model=list[SiteStats])
async def site_stats(_token: str = Depends(require_auth)) -> list[SiteStats]:
    """How many times each registered website has actually been tested -
    the sidebar's "tested N times" summary."""
    return await history.site_stats()


@app.get("/api/history/{run_id}", response_model=HistoryDetail)
async def get_history_entry(run_id: int, _token: str = Depends(require_auth)) -> HistoryDetail:
    entry = await history.get_run(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return entry


@app.get("/api/history/{run_id}/report.pdf")
async def get_history_report_pdf(run_id: int, _token: str = Depends(require_auth)) -> Response:
    """A downloadable, standalone version of one run's report - timestamps,
    metrics charts and tables, findings, plus a short Claude-written
    narrative - for handing to someone who wasn't watching the dashboard."""
    entry = await history.get_run(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    pdf_bytes = await generate_report_pdf(entry)
    filename = f"protester-report-{entry.ticket_id}-{run_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


@app.post("/api/history/{run_id}/ask", response_model=AskResponse)
async def ask_about_report(run_id: int, body: AskRequest, _token: str = Depends(require_auth)) -> AskResponse:
    """Answers a free-form question about one run, grounded in its actual
    stored report - not a general chat, so it can't answer anything the
    report itself doesn't contain."""
    entry = await history.get_run(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    try:
        llm = ClaudeLLMClient()
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    prompt = f"""You are answering a question about one QA test run, using ONLY the data
below - if the answer isn't in this data, say so plainly instead of guessing.

Run data (JSON): {json.dumps(entry.result)[:6000]}

Question: {body.question}

Answer in 2-4 plain sentences, no other text.
"""
    try:
        response = await llm.complete(prompt, max_tokens=300, timeout=20)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AskResponse(answer=response.text)


@app.get("/api/domains", response_model=list[Domain])
async def list_domains(_token: str = Depends(require_auth)) -> list[Domain]:
    """Everything the Planner/Explorer/Verifier can currently test against -
    what the dashboard's Domain Knowledge page shows before you add to it."""
    return load_domains()


class WorkflowIn(BaseModel):
    name: str
    steps: list[str]
    url_contains: str | None = None
    text_contains: str | None = None


class DomainKnowledgeIn(BaseModel):
    domain: str
    base_url: str = ""  # only required when domain is new - ignored for an existing one
    workflow: WorkflowIn


@app.post("/api/domains", response_model=Domain)
async def add_domain_knowledge(body: DomainKnowledgeIn, _token: str = Depends(require_auth)) -> Domain:
    """Adds one workflow to a domain from the dashboard instead of hand-
    editing a YAML file - the same "no domain knowledge for this target"
    gap the Planner reports on an unmatched ticket, closed live. Writes
    straight to the same domain knowledge store the Planner reads, so a
    ticket can reference what was just added immediately, no restart
    needed (unlike credentials baked into a workflow's steps at YAML
    creation time - those still need editing directly)."""
    if not body.domain.strip():
        raise HTTPException(status_code=400, detail="Domain name is required.")
    if not body.workflow.name.strip():
        raise HTTPException(status_code=400, detail="Workflow name is required.")

    steps = [s.strip() for s in body.workflow.steps if s.strip()]
    if not steps:
        raise HTTPException(status_code=400, detail="At least one step is required.")

    url_contains = (body.workflow.url_contains or "").strip() or None
    text_contains = (body.workflow.text_contains or "").strip() or None
    if not url_contains and not text_contains:
        raise HTTPException(
            status_code=400, detail="Provide at least one of url_contains or text_contains, or nothing can ever verify this workflow."
        )

    existing = next((d for d in load_domains() if d.name == slugify(body.domain)), None)
    if existing is None and not body.base_url.strip():
        raise HTTPException(status_code=400, detail="base_url is required when registering a new domain.")

    workflow = Workflow(
        name=slugify(body.workflow.name),
        steps=steps,
        expected_outcome=ExpectedOutcome(url_contains=url_contains, text_contains=text_contains),
    )
    return save_workflow(body.domain, body.base_url, workflow)


class TrelloStatus(BaseModel):
    connected: bool
    source: str  # "settings" | "env" | "none" - where the active credentials (if any) come from


class TrelloSettingsIn(BaseModel):
    api_key: str
    token: str


def _trello_status() -> TrelloStatus:
    if load_trello_settings() is not None:
        return TrelloStatus(connected=True, source="settings")
    if os.environ.get("TRELLO_API_KEY") and os.environ.get("TRELLO_TOKEN"):
        return TrelloStatus(connected=True, source="env")
    return TrelloStatus(connected=False, source="none")


@app.get("/api/trello/status", response_model=TrelloStatus)
async def trello_status(_token: str = Depends(require_auth)) -> TrelloStatus:
    """Whether Trello is currently connected, and where the active
    credentials came from - never returns the key/token themselves, only
    whether something's configured, so a secret is never sent back down
    to the browser after being saved."""
    return _trello_status()


@app.post("/api/trello/settings", response_model=TrelloStatus)
async def save_trello_credentials(body: TrelloSettingsIn, _token: str = Depends(require_auth)) -> TrelloStatus:
    """Saves a Trello API key/token from the dashboard instead of
    requiring a backend .env file - the gap a hosted, non-technical user
    would otherwise hit with no filesystem access. One shared connection
    at a time (this app has one login, not per-user accounts) - saving a
    new one replaces whatever was previously connected. Verified against
    Trello's real API before being saved - a typo or a placeholder value
    would otherwise silently "connect" until the first real ticket run
    failed on it."""
    api_key = body.api_key.strip()
    token = body.token.strip()
    if not api_key or not token:
        raise HTTPException(status_code=400, detail="Both an API key and a token are required.")
    try:
        await verify_trello_credentials(api_key, token)
    except TrelloError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_trello_settings(api_key, token)
    return _trello_status()


@app.delete("/api/trello/settings", response_model=TrelloStatus)
async def disconnect_trello(_token: str = Depends(require_auth)) -> TrelloStatus:
    """Disconnects the currently-saved Trello connection. Falls back to
    TRELLO_API_KEY/TRELLO_TOKEN env vars afterward if those are set,
    same as if nothing had ever been saved from the dashboard."""
    clear_trello_settings()
    return _trello_status()


class SmokeWorkflowOut(BaseModel):
    domain: str
    workflow: str


class SmokeCycleErrorOut(BaseModel):
    domain: str
    workflow: str
    error: str


class SmokeCycleOut(BaseModel):
    triggered_by: str
    provider: str
    started_at: float
    finished_at: float
    pass_count: int
    fail_count: int
    run_ids: list[int]
    errors: list[SmokeCycleErrorOut]


class SchedulerStatus(BaseModel):
    enabled: bool
    interval_minutes: int
    provider: str
    next_run_at: float | None
    smoke_workflows: list[SmokeWorkflowOut]
    last_cycle: SmokeCycleOut | None


def _cycle_out(cycle) -> SmokeCycleOut | None:
    if cycle is None:
        return None
    return SmokeCycleOut(
        triggered_by=cycle.triggered_by,
        provider=cycle.provider,
        started_at=cycle.started_at,
        finished_at=cycle.finished_at,
        pass_count=cycle.pass_count,
        fail_count=cycle.fail_count,
        run_ids=cycle.run_ids,
        errors=[SmokeCycleErrorOut(domain=e.domain, workflow=e.workflow, error=e.error) for e in cycle.errors],
    )


@app.get("/api/scheduler/status", response_model=SchedulerStatus)
async def scheduler_status(_token: str = Depends(require_auth)) -> SchedulerStatus:
    """What the dashboard's Scheduler panel shows: the fixed interval this
    runs on, every domain's smoke-flagged workflows, when the next
    unattended cycle fires, and the outcome of the last cycle - whichever
    triggered it, scheduled or on-demand, since both write to the same
    last_cycle."""
    return SchedulerStatus(
        enabled=smoke_scheduler.running,
        interval_minutes=smoke_scheduler.interval_minutes,
        provider=smoke_scheduler.provider,
        next_run_at=smoke_scheduler.next_run_at,
        smoke_workflows=[SmokeWorkflowOut(domain=r.domain, workflow=r.workflow) for r in list_smoke_workflows()],
        last_cycle=_cycle_out(smoke_scheduler.last_cycle),
    )


@app.post("/api/scheduler/run-now", response_model=SmokeCycleOut)
async def scheduler_run_now(_token: str = Depends(require_auth)) -> SmokeCycleOut:
    """On-demand trigger for the dashboard - calls the exact same
    run_cycle() a scheduled tick calls, just started by a button instead
    of the interval timer. Same execution path, different trigger."""
    cycle = await smoke_scheduler.run_now()
    return _cycle_out(cycle)


CHAT_HISTORY_LIMIT = 12  # turns kept in the prompt, not stored server-side


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    # Set only when the assistant detected a clear "run/test this ticket"
    # request - the frontend uses these to actually start the run through
    # the same WebSocket pipeline a manual "New Test" submit would, rather
    # than the chat pretending to run something it can't.
    action: str | None = None  # "run_ticket" | None
    ticket_id: str | None = None
    model: str | None = None  # "claude" | "ollama" | "both"


_CHAT_VALID_MODELS = {"claude", "ollama", "both"}


def _system_facts_for_chat() -> str:
    """Real, current facts about this exact system - grounds the
    assistant's answers about "how does this work" in what's actually
    true right now (registered domains especially, which change over
    time) instead of generic AI filler about QA tools in general."""
    domains = load_domains()
    domain_lines = "\n".join(f"- {d.name} ({d.base_url}): {', '.join(w.name for w in d.workflows)}" for d in domains)
    return f"""ProTester is a four-agent AI QA testing pipeline:
- Planner: reads a Trello ticket, matches it against the registered domain/workflow manifest below, builds a test plan.
- Explorer: drives a real Playwright browser, deciding each next action from the live page state (not a fixed script).
- Verifier: re-checks a flagged result once before it's accepted as confirmed.
- Reporter: writes the final report and posts a summary comment back to the originating Trello ticket.

Two LLM providers, split by cost/call-volume: Claude (Anthropic) drives the Planner, Verifier, and
Reporter's judgment-heavy, low-call-volume work; Llama (via local Ollama or Groq's hosted API) drives
the Explorer's frequent, low-stakes per-action decisions. The user can run a ticket on Claude, Llama, or
both side by side (a "Compare Mode" that shows a head-to-head on accuracy, coverage, latency, and cost).

Backend: FastAPI (Python) + SQLite for run history. Frontend: React + TypeScript + Vite. Browser
automation: Playwright. A WebSocket streams each agent's live status, screenshots, and the final report.

Currently registered domains and workflows (this is the complete, real, current list - nothing else can
be tested until it's added via the Domain Knowledge page):
{domain_lines or "(none registered yet)"}
"""


CHAT_RECENT_RUNS_LIMIT = 5


async def _recent_runs_context() -> str:
    """Real facts (verdict, the Verifier's explanation, and every
    finding's real summary/error) about the most recent runs - without
    this, "why did that fail" has nothing grounded to answer from and
    either declines or has to invent a reason, the same "never guess"
    problem every other agent in this system already avoids by only
    ever reporting what it actually observed."""
    entries = await history.list_runs(limit=CHAT_RECENT_RUNS_LIMIT)
    if not entries:
        return "No test runs have been recorded yet."

    lines = []
    for entry in entries:
        detail = await history.get_run(entry.id)
        if detail is None:
            continue
        result = detail.result
        verification = result.get("verification") or {}
        findings = ((result.get("report") or {}).get("findings")) or []
        finding_text = "; ".join(
            f"[{f.get('severity')}] {f.get('summary')}" + (f" (error: {f.get('error_message')})" if f.get("error_message") else "")
            for f in findings
        )
        line = (
            f"- Run #{entry.id}, ticket {entry.ticket_id} ({entry.domain or '?'}/{entry.workflow or '?'} "
            f"on {entry.provider}): verdict {entry.verdict or 'n/a'}."
        )
        if verification.get("explanation"):
            line += f" Verifier said: {verification['explanation']!r}."
        if finding_text:
            line += f" Findings: {finding_text}"
        lines.append(line)
    return "\n".join(lines)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, _token: str = Depends(require_auth)) -> ChatResponse:
    """A general-purpose assistant, unlike /ask which only answers from one
    run's report - this one can talk about anything, the same way any
    Claude chat would, AND can start a ticket run when asked in plain
    language. Stateless on the backend; the client resends the running
    conversation each turn."""
    try:
        llm = ClaudeLLMClient()
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    transcript = "\n".join(f"{m.role.capitalize()}: {m.content}" for m in body.history[-CHAT_HISTORY_LIMIT:])
    prompt = f"""You are the assistant built into ProTester, an AI-powered QA testing dashboard. You can
help with anything the user asks, not only QA/testing topics, AND you can answer accurately about how
this exact system works using the real facts below - never invent architecture details not listed here.

{_system_facts_for_chat()}

Most recent test runs, newest first - use this to answer "why did that fail / pass" questions with the
REAL reason, grounded in what actually happened (the Verifier's explanation and the Reporter's findings
below), not a generic non-answer. If the user's question is clearly about their most recent run, assume
they mean the run listed first. Give a direct, short answer (one or two sentences is fine) instead of
saying you don't have the report in front of you when it's right here. Only say you don't know if
nothing below actually covers what's asked:
{await _recent_runs_context()}

You can also START a real test run when the user clearly asks to run/test a ticket in plain language
(e.g. "run ticket ABC123", "test the toolshop login on both models"), as long as they give or clearly
imply a ticket ID.

{transcript}
User: {body.message}

Respond with ONLY a JSON object, no other text, no markdown fences, in exactly one of these two shapes:
1. Just answering: {{"intent": "chat", "reply": "<conversational answer, no preamble like 'Sure!'>"}}
2. Starting a run (only when a ticket ID is given or clearly implied): {{"intent": "run_ticket",
   "ticket_id": "<the ticket id>", "model": "claude"|"ollama"|"both"|null,
   "reply": "<short confirmation, e.g. 'Starting a Claude run for ticket ABC123 now.'>"}}
If they ask to run something but give no identifiable ticket ID, use "chat" and ask for it instead.
"""
    try:
        response = await llm.complete(prompt, max_tokens=400, timeout=25)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Answered in plain prose instead of the requested JSON shape -
        # still a perfectly good chat answer, shown directly rather than
        # failing the whole request over a formatting near-miss.
        return ChatResponse(reply=response.text.strip())

    if parsed.get("intent") == "run_ticket" and parsed.get("ticket_id"):
        model = parsed.get("model") if parsed.get("model") in _CHAT_VALID_MODELS else "claude"
        ticket_id = str(parsed["ticket_id"])
        return ChatResponse(
            reply=str(parsed.get("reply") or f"Starting a {model} run for ticket {ticket_id} now."),
            action="run_ticket",
            ticket_id=ticket_id,
            model=model,
        )

    return ChatResponse(reply=str(parsed.get("reply") or response.text.strip()))
