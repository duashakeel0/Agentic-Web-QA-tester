"""Day 1 scaffolded the pipeline with mock data. Day 2 added a real browser
driver behind a WebSocket for one-off page loads. /ws/pipeline is the real
thing: it drives the full Planner -> Explorer -> Verifier -> Reporter
pipeline against a Trello ticket, with a model choice (Claude, Ollama, or
both side by side), streaming each agent's status live instead of returning
one final blob.
"""

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agents.pipeline import run_both, run_pipeline
from app.browser import BrowserSession

load_dotenv()

app = FastAPI(title="Agentic Web QA Tester")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
async def run_pipeline_ws(websocket: WebSocket) -> None:
    """Client sends {"ticket_id": "...", "model": "claude"|"ollama"|"both"}
    once, then receives a stream of stage_start/stage_end/stage_error events
    as the pipeline runs, followed by one pipeline_done per provider and
    (for "both") one comparison_done."""
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
            await websocket.send_json(
                {"type": "pipeline_done", "provider": "claude", "result": claude_result.model_dump(mode="json")}
            )
            await websocket.send_json(
                {"type": "pipeline_done", "provider": "ollama", "result": ollama_result.model_dump(mode="json")}
            )
            await websocket.send_json({"type": "comparison_done", "comparison": comparison.model_dump(mode="json")})
        else:
            result = await run_pipeline(ticket_id, model, on_event=on_event)
            await websocket.send_json(
                {"type": "pipeline_done", "provider": model, "result": result.model_dump(mode="json")}
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
