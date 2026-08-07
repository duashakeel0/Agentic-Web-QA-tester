"""Builds the downloadable PDF version of a completed run - the thing you'd
actually hand to someone who wasn't watching the dashboard live. Combines
the stored run data with a short Claude-written narrative, laid out with
reportlab (tables + a couple of bar charts, no external renderer needed).
"""

import io
import json
import os
import time

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.agents.claude_client import ClaudeLLMClient
from app.agents.llm_client import LLMError
from app.history.schema import HistoryDetail

_PASS_COLOR_HEX = "#0ca30c"
_FAIL_COLOR_HEX = "#d03b3b"
_PASS_COLOR = colors.HexColor(_PASS_COLOR_HEX)
_FAIL_COLOR = colors.HexColor(_FAIL_COLOR_HEX)
_ACCENT = colors.HexColor("#4a3aa7")
_GRID = colors.HexColor("#cccccc")

# Screenshots are served from main.py's /screenshots static mount, but the
# PDF needs the real file on disk - this is that mount's target directory,
# kept in sync with main.py's SCREENSHOTS_DIR by convention (both point at
# the same gitignored reports/screenshots/ folder).
_SCREENSHOTS_DIR = "reports/screenshots"
_MAX_REPORT_SCREENSHOTS = 12
_SCREENSHOT_WIDTH = 3.4 * inch


def _screenshot_disk_path(screenshot_url: str | None) -> str | None:
    if not screenshot_url or not screenshot_url.startswith("/screenshots/"):
        return None
    return os.path.join(_SCREENSHOTS_DIR, screenshot_url.removeprefix("/screenshots/"))


def _sized_image(path: str, max_width: float) -> Image | None:
    """A width-capped Image flowable at the screenshot's real aspect ratio -
    reportlab's Image() otherwise renders at native pixel-as-point size,
    which is far too large for a report page."""
    try:
        reader = ImageReader(path)
        native_width, native_height = reader.getSize()
        if not native_width:
            return None
        return Image(path, width=max_width, height=max_width * native_height / native_width)
    except Exception:
        return None


def _fmt_ts(unix_ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(unix_ts))


async def _generate_narrative(entry: HistoryDetail) -> dict:
    """A short, Claude-written analysis of this one run - falls back to a
    plain factual summary (no LLM call) if Claude is unavailable, so a
    missing API key never blocks the export itself."""
    fallback = {
        "executive_summary": (
            f"{entry.ticket_id} on {entry.provider} finished with verdict "
            f"'{entry.verdict or 'n/a'}' in {entry.total_duration_ms / 1000:.1f}s."
        ),
        "analysis": "Automated narrative unavailable - Claude was not reachable when this report was generated.",
        "recommendation": "Review the findings and action log below directly.",
    }
    try:
        llm = ClaudeLLMClient()
    except LLMError:
        return fallback

    prompt = f"""You are writing a section of a formal QA test report for a non-technical
reader, based only on the run data below - do not invent facts not present in it.

Run data (JSON): {json.dumps(entry.result)[:6000]}

Return ONLY valid JSON with exactly these three keys, no other text, no markdown fences:
{{"executive_summary": "2-3 sentences, what was tested and the outcome",
  "analysis": "3-5 sentences on why it passed/failed and what the findings mean",
  "recommendation": "1-3 sentences on what to do next"}}
"""
    try:
        response = await llm.complete(prompt, max_tokens=500, timeout=25)
        text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(text)
        return {k: str(parsed.get(k, fallback[k])) for k in fallback}
    except (LLMError, json.JSONDecodeError, ValueError):
        return fallback


def _bar_chart(pairs: list[tuple[str, float]], width: float = 380, height: float = 140) -> Drawing:
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x, chart.y = 40, 20
    chart.width, chart.height = width - 60, height - 40
    chart.data = [[value for _, value in pairs]]
    chart.categoryAxis.categoryNames = [label for label, _ in pairs]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = 100
    chart.bars[0].fillColor = _ACCENT
    chart.barLabels.nudge = 7
    chart.barLabelFormat = "%0.0f%%"
    chart.barLabels.visible = True
    drawing.add(chart)
    return drawing


def build_pdf(entry: HistoryDetail, narrative: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch, leftMargin=0.7 * inch, rightMargin=0.7 * inch
    )
    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=6, textColor=_ACCENT)
    body = styles["BodyText"]

    result = entry.result
    plan = result.get("plan", {})
    metrics = result.get("metrics") or {}
    report = result.get("report") or {}
    timings = result.get("timings") or []
    verdict = entry.verdict or "n/a"
    verdict_color = _PASS_COLOR if verdict == "pass" else _FAIL_COLOR

    story = [
        Paragraph("SentinelQA Test Report", h1),
        Paragraph(f"Generated {_fmt_ts(time.time())}", styles["Normal"]),
        Spacer(1, 12),
    ]

    summary_rows = [
        ["Ticket ID", entry.ticket_id],
        ["Ticket title", plan.get("ticket_title") or "n/a"],
        ["Website / workflow", f"{entry.domain or 'n/a'} - {entry.workflow or 'n/a'}"],
        ["Model", entry.provider],
        ["Verdict", verdict.upper()],
        ["Started", _fmt_ts(entry.started_at)],
        ["Finished", _fmt_ts(entry.finished_at)],
        ["Total duration", f"{entry.total_duration_ms / 1000:.1f}s"],
        ["Estimated cost", f"${entry.estimated_cost_usd:.4f}"],
    ]
    summary_table = Table(summary_rows, colWidths=[150, 320])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("TEXTCOLOR", (1, 4), (1, 4), verdict_color),
                ("FONTNAME", (1, 4), (1, 4), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary_table)

    story.append(Paragraph("Executive summary", h2))
    story.append(Paragraph(narrative["executive_summary"], body))
    story.append(Paragraph("Analysis", h2))
    story.append(Paragraph(narrative["analysis"], body))
    story.append(Paragraph("Recommendation", h2))
    story.append(Paragraph(narrative["recommendation"], body))

    if metrics:
        story.append(Paragraph("Quality metrics", h2))
        story.append(
            _bar_chart(
                [
                    ("Coverage", round(metrics.get("coverage_ratio", 0) * 100, 1)),
                    ("Accuracy", round(metrics.get("accuracy_ratio", 0) * 100, 1)),
                ]
            )
        )
        metrics_rows = [
            ["Steps covered", f"{metrics.get('steps_covered', 0)}/{metrics.get('steps_planned', 0)}"],
            ["Actions succeeded", f"{metrics.get('actions_succeeded', 0)}/{metrics.get('actions_attempted', 0)}"],
            ["Model calls", str(metrics.get("llm_call_count", 0))],
            ["Tokens (in/out)", f"{metrics.get('input_tokens', 0)} / {metrics.get('output_tokens', 0)}"],
        ]
        metrics_table = Table(metrics_rows, colWidths=[150, 320])
        metrics_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(Spacer(1, 6))
        story.append(metrics_table)

    if timings:
        story.append(Paragraph("Stage timings", h2))
        timing_rows = [["Agent", "Model", "Started", "Finished", "Duration"]]
        for t in timings:
            timing_rows.append(
                [
                    t["agent"].capitalize(),
                    t["model"],
                    _fmt_ts(t["started_at"]),
                    _fmt_ts(t["finished_at"]),
                    f"{t['duration_ms'] / 1000:.1f}s",
                ]
            )
        timing_table = Table(timing_rows, colWidths=[70, 90, 130, 130, 55])
        timing_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(timing_table)

    findings = report.get("findings") or []
    if findings:
        story.append(Paragraph("Findings", h2))
        finding_rows = [["Severity", "Summary", "Error"]]
        for f in findings:
            finding_rows.append(
                [f["severity"].upper(), Paragraph(f["summary"], body), Paragraph(f.get("error_message") or "-", body)]
            )
        finding_table = Table(finding_rows, colWidths=[60, 230, 180])
        finding_table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(finding_table)

    action_entries = (result.get("exploration") or {}).get("actions") or []
    screenshotted = [a for a in action_entries if a.get("screenshot_path")][:_MAX_REPORT_SCREENSHOTS]
    if screenshotted:
        story.append(Paragraph("Action Screenshots", h2))
        for a in screenshotted:
            path = _screenshot_disk_path(a.get("screenshot_path"))
            if not path or not os.path.isfile(path):
                continue
            image = _sized_image(path, _SCREENSHOT_WIDTH)
            if image is None:
                continue
            caption = f"{a['step']} — {a['action']}"
            if a.get("selector"):
                caption += f" on {a['selector']}"
            status = "PASS" if a.get("success") else f"FAIL ({a.get('error') or 'no detail'})"
            status_color_hex = _PASS_COLOR_HEX if a.get("success") else _FAIL_COLOR_HEX
            story.append(Paragraph(f'{caption} — <font color="{status_color_hex}">{status}</font>', body))
            story.append(image)
            story.append(Spacer(1, 10))

    doc.build(story)
    return buffer.getvalue()


async def generate_report_pdf(entry: HistoryDetail) -> bytes:
    narrative = await _generate_narrative(entry)
    return build_pdf(entry, narrative)
