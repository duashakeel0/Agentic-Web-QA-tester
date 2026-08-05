"""Day 1 scaffolded the pipeline with mock data. Day 2 added a real browser
driver behind a WebSocket for one-off page loads. /ws/pipeline is the real
thing: it drives the full Planner -> Explorer -> Verifier -> Reporter
pipeline against a Trello ticket, with a model choice (Claude, Ollama, or
both side by side), streaming each agent's status live instead of returning
one final blob.
"""

import json
import sys

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
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents.claude_client import ClaudeLLMClient
from app.agents.llm_client import LLMError
from app.agents.pipeline import run_both, run_pipeline
from app.auth import AuthError, login as auth_login, logout as auth_logout, require_auth, require_auth_ws
from app.browser import BrowserSession
from app.history.schema import ComparisonHistoryEntry, DailyStat, HistoryDetail, HistoryEntry, HistoryStats, ProviderStats
from app.history.store import HistoryStore

load_dotenv()

app = FastAPI(title="SentinelQA")
history = HistoryStore()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    as the pipeline runs, followed by one pipeline_done per provider and
    (for "both") one comparison_done. Connect as /ws/pipeline?token=<token>
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


@app.get("/api/history/{run_id}", response_model=HistoryDetail)
async def get_history_entry(run_id: int, _token: str = Depends(require_auth)) -> HistoryDetail:
    entry = await history.get_run(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return entry


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


CHAT_HISTORY_LIMIT = 12  # turns kept in the prompt, not stored server-side


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, _token: str = Depends(require_auth)) -> ChatResponse:
    """A general-purpose assistant, unlike /ask which only answers from one
    run's report - this one can talk about anything, the same way any
    Claude chat would. Stateless on the backend; the client resends the
    running conversation each turn."""
    try:
        llm = ClaudeLLMClient()
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    transcript = "\n".join(f"{m.role.capitalize()}: {m.content}" for m in body.history[-CHAT_HISTORY_LIMIT:])
    prompt = f"""You are the assistant built into SentinelQA, an AI-powered QA testing dashboard.
You can help with anything the user asks, not only QA/testing topics - answer like a
general-purpose, knowledgeable assistant would.

{transcript}
User: {body.message}

Respond directly and conversationally, no preamble like "Sure!" or "Here's the answer:".
"""
    try:
        response = await llm.complete(prompt, max_tokens=600, timeout=25)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(reply=response.text)
