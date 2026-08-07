from PIL import Image as PILImage

from app.history.schema import HistoryDetail
from app.pdf_report import build_pdf

_NARRATIVE = {
    "executive_summary": "Summary.",
    "analysis": "Analysis.",
    "recommendation": "Recommendation.",
}


def _entry(result: dict) -> HistoryDetail:
    return HistoryDetail(
        id=1,
        ticket_id="T1",
        domain="sauce_demo",
        workflow="login",
        provider="ollama",
        matched=True,
        verdict="pass",
        findings_count=0,
        total_duration_ms=1000.0,
        estimated_cost_usd=0.0,
        started_at=0.0,
        finished_at=1.0,
        created_at=1.0,
        result=result,
    )


def test_build_pdf_embeds_action_screenshots(tmp_path, monkeypatch):
    import app.pdf_report as pdf_report

    monkeypatch.setattr(pdf_report, "_SCREENSHOTS_DIR", str(tmp_path))
    screenshot_dir = tmp_path / "actions"
    screenshot_dir.mkdir()
    PILImage.new("RGB", (400, 300), color="white").save(screenshot_dir / "shot1.png")

    result = {
        "plan": {"ticket_title": "Login test"},
        "metrics": {},
        "report": {"findings": []},
        "timings": [],
        "exploration": {
            "actions": [
                {
                    "step": "Fill username",
                    "action": "fill",
                    "selector": "#user-name",
                    "success": True,
                    "error": None,
                    "screenshot_path": "/screenshots/actions/shot1.png",
                },
                {
                    "step": "Missing screenshot step",
                    "action": "click",
                    "selector": "#missing",
                    "success": False,
                    "error": "boom",
                    "screenshot_path": "/screenshots/actions/does-not-exist.png",
                },
            ]
        },
    }

    pdf_bytes = build_pdf(_entry(result), _NARRATIVE)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_build_pdf_skips_gracefully_with_no_screenshots():
    result = {
        "plan": {"ticket_title": "Login test"},
        "metrics": {},
        "report": {"findings": []},
        "timings": [],
        "exploration": {"actions": []},
    }

    pdf_bytes = build_pdf(_entry(result), _NARRATIVE)

    assert pdf_bytes.startswith(b"%PDF")
