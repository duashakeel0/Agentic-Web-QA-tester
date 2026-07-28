"""Day 1 scaffolded the pipeline with mock data. Day 2 adds a real browser
driver (Playwright) behind a WebSocket, so the dashboard gets live status
updates as an actual page loads instead of one static fetch. Real agent
logic (Planner, Explorer, Verifier, Reporter) is built out in future
milestones.
"""

from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.browser import BrowserSession

load_dotenv()

API_VERSION = "0.1.0"

app = FastAPI(title="Agentic Web QA Tester", version=API_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TestRunResult(BaseModel):
    status: str
    pages_visited: int
    actions_taken: int
    bugs_found: int
    summary: str


def _is_valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "service": "agentic-web-qa-tester-backend", "version": API_VERSION}


@app.get("/api/v1/mock-run", response_model=TestRunResult)
def mock_run() -> TestRunResult:
    """Stands in for a real test run until the Explorer/Verifier/Reporter
    agents exist (future milestones). Returns a fixed, fake result so the
    frontend has something real to fetch and render end to end."""
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
        if not _is_valid_http_url(url):
            await websocket.send_json(
                {"type": "error", "message": f"'{url}' is not a valid http:// or https:// URL."}
            )
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
