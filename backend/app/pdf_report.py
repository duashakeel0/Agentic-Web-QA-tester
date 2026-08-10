"""Builds the downloadable PDF version of a completed run - the thing you'd
actually hand to someone who wasn't watching the dashboard live. Laid out
like a standard QA test execution report (test info, execution summary
with charts, a step-by-step test case table, defects, timings, evidence)
rather than an ad-hoc dump of the run data, combined with a short
Claude-written narrative and built with reportlab (tables + charts, no
external renderer needed).
"""

import io
import json
import os
import time

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
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
_WARN_COLOR_HEX = "#c98a1f"
_FAIL_COLOR_HEX = "#d03b3b"
_PASS_COLOR = colors.HexColor(_PASS_COLOR_HEX)
_WARN_COLOR = colors.HexColor(_WARN_COLOR_HEX)
_FAIL_COLOR = colors.HexColor(_FAIL_COLOR_HEX)
_SKIP_COLOR = colors.HexColor("#8a8a8a")
_ACCENT = colors.HexColor("#4a3aa7")
_GRID = colors.HexColor("#cccccc")

_VERDICT_COLORS = {"pass": _PASS_COLOR, "pass_with_issues": _WARN_COLOR, "fail": _FAIL_COLOR}
_STEP_STATUS_COLORS = {"PASS": _PASS_COLOR, "FAIL": _FAIL_COLOR, "SKIPPED": _SKIP_COLOR, "NOT REACHED": _SKIP_COLOR}

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


def _format_expected_outcome(expected: dict | None) -> str:
    if not expected:
        return "n/a"
    parts = []
    if expected.get("url_contains"):
        parts.append(f'the URL contains "{expected["url_contains"]}"')
    if expected.get("text_contains"):
        parts.append(f'the page text contains "{expected["text_contains"]}"')
    return " AND ".join(parts) if parts else "n/a"


def _step_rows(plan: dict, exploration: dict | None, verdict: str | None = None) -> list[dict]:
    """One row per planned test step, derived entirely from the real action
    log rather than fabricated - a step with no actions at all is either
    "skipped" (already satisfied when the page loaded, only possible for a
    completed run) or "not reached" (exploration stopped before it)."""
    steps = plan.get("steps") or []
    actions = (exploration or {}).get("actions") or []
    completed = bool((exploration or {}).get("completed"))
    real_actions = [a for a in actions if not a.get("is_broken_input_attempt")]
    # When the workflow ran to completion (every step's action executed
    # with no error) but the overall verdict is still "fail", the
    # expected outcome was never actually reached - a real ParaBank/
    # Toolshop-style login case: the click succeeds mechanically, but the
    # site never authenticates. Every earlier step genuinely achieved its
    # own local goal (a field got filled); it's specifically the last
    # real action taken - the one the final assertion actually depends
    # on - whose "PASS" is misleading next to an overall FAIL badge.
    # Marked here, not just left to the Findings section, since a step
    # table that shows a clean sweep right above a FAIL verdict reads as
    # a contradiction rather than "the click worked, the login didn't."
    failed_step = real_actions[-1]["step"] if (completed and verdict == "fail" and real_actions) else None

    rows = []
    for step in steps:
        step_actions = [a for a in actions if a.get("step") == step and not a.get("is_broken_input_attempt")]
        if not step_actions:
            if completed:
                status, note = "SKIPPED", "Already satisfied when the page loaded - no action needed."
            else:
                status, note = "NOT REACHED", "Exploration stopped before this step was attempted."
        elif step == failed_step:
            status = "FAIL"
            note = "The action completed, but did not achieve the expected outcome - see Findings below."
        else:
            # A step's real outcome is whether it was ever actually
            # achieved, not whether its literal last logged attempt
            # happened to succeed - a step can (and often does) need a
            # retry, and an unrelated hiccup on a later, redundant attempt
            # after the step already succeeded must never flip a genuinely
            # completed step to FAIL. Only "every attempt failed" is real.
            if any(a.get("success") for a in step_actions):
                status = "PASS"
                note = f"Completed successfully in {len(step_actions)} action(s)."
            else:
                status = "FAIL"
                note = step_actions[-1].get("error") or "Action failed with no further detail."
        rows.append({"step": step, "status": status, "note": note})
    return rows


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


def _pass_fail_pie(passed: int, failed: int, width: float = 220, height: float = 130) -> Drawing:
    """Donut-style pass/fail breakdown for the actions actually attempted -
    the same shape as the dashboard's own DonutChart, just rendered for a
    static PDF page instead of the live UI."""
    drawing = Drawing(width, height)
    pie = Pie()
    pie.x, pie.y = 10, 5
    pie.width = pie.height = 110
    pie.innerRadiusFraction = 0.55
    pie.sideLabels = True
    pie.simpleLabels = False
    pie.slices.strokeWidth = 0.5
    pie.slices.strokeColor = colors.white

    total = passed + failed
    if total == 0:
        pie.data = [1]
        pie.labels = ["No actions recorded"]
        pie.slices[0].fillColor = _GRID
    else:
        pie.data = [passed, failed]
        pie.labels = [f"Passed ({passed})", f"Failed ({failed})"]
        pie.slices[0].fillColor = _PASS_COLOR
        pie.slices[1].fillColor = _FAIL_COLOR
    drawing.add(pie)
    return drawing


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


def build_pdf(entry: HistoryDetail, narrative: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch, leftMargin=0.7 * inch, rightMargin=0.7 * inch
    )
    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=6, textColor=_ACCENT)
    subtitle = ParagraphStyle("Subtitle", parent=styles["Normal"], textColor=colors.grey, spaceAfter=4)
    body = styles["BodyText"]
    small = ParagraphStyle("Small", parent=body, fontSize=8.5, leading=11)

    result = entry.result
    plan = result.get("plan", {})
    exploration = result.get("exploration") or {}
    metrics = result.get("metrics") or {}
    report = result.get("report") or {}
    timings = result.get("timings") or []
    verification = result.get("verification") or {}
    verdict = entry.verdict or "n/a"
    verdict_color = _VERDICT_COLORS.get(verdict, _FAIL_COLOR)

    story = [
        Paragraph("SentinelQA — QA Test Execution Report", h1),
        Paragraph("Automated Functional Test, executed by an AI QA agent", subtitle),
        Paragraph(f"Report generated {_fmt_ts(time.time())}", styles["Normal"]),
        Spacer(1, 12),
    ]

    # ---- Test information -------------------------------------------------
    story.append(Paragraph("1. Test Information", h2))
    info_rows = [
        ["Ticket ID", entry.ticket_id],
        ["Ticket title", plan.get("ticket_title") or "n/a"],
        ["Module / feature under test", f"{entry.domain or 'n/a'} — {entry.workflow or 'n/a'}"],
        ["Test type", "Automated functional test (AI QA agent)"],
        ["Model / agent", entry.provider],
        ["Test executed", f"{_fmt_ts(entry.started_at)} — {_fmt_ts(entry.finished_at)}"],
        ["Total duration", f"{entry.total_duration_ms / 1000:.1f}s"],
        ["Estimated cost", f"${entry.estimated_cost_usd:.4f}"],
        ["Overall result", verdict.replace("_", " ").upper()],
    ]
    info_table = Table(info_rows, colWidths=[160, 310])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("TEXTCOLOR", (1, 8), (1, 8), verdict_color),
                ("FONTNAME", (1, 8), (1, 8), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(info_table)

    # ---- Test execution summary -------------------------------------------
    story.append(Paragraph("2. Test Execution Summary", h2))
    step_rows = _step_rows(plan, exploration, verdict)
    steps_passed = sum(1 for r in step_rows if r["status"] == "PASS")
    steps_failed = sum(1 for r in step_rows if r["status"] == "FAIL")
    actions_attempted = int(metrics.get("actions_attempted", 0))
    actions_succeeded = int(metrics.get("actions_succeeded", 0))
    actions_failed = actions_attempted - actions_succeeded

    summary_counts = Table(
        [
            ["Total test steps", str(len(step_rows))],
            ["Steps passed", str(steps_passed)],
            ["Steps failed", str(steps_failed)],
            ["Steps skipped / not reached", str(len(step_rows) - steps_passed - steps_failed)],
            ["Total actions attempted", str(actions_attempted)],
            ["Pass rate (actions)", f"{metrics.get('accuracy_ratio', 0) * 100:.0f}%"],
        ],
        colWidths=[150, 70],
    )
    summary_counts.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    summary_row = Table(
        [[_pass_fail_pie(actions_succeeded, max(actions_failed, 0)), summary_counts]],
        colWidths=[230, 240],
    )
    summary_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story.append(summary_row)

    # ---- Expected vs. actual outcome --------------------------------------
    story.append(Paragraph("3. Expected vs. Actual Outcome", h2))
    actual_text = verification.get("explanation") or (
        "Assertion held." if verification.get("initial_check_passed") or verification.get("retry_passed") else "Assertion did not hold."
    )
    outcome_rows = [
        ["Expected", Paragraph(_format_expected_outcome(plan.get("expected_outcome")), body)],
        ["Actual", Paragraph(actual_text, body)],
        ["Result", verdict.replace("_", " ").upper()],
    ]
    outcome_table = Table(outcome_rows, colWidths=[80, 390])
    outcome_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TEXTCOLOR", (1, 2), (1, 2), verdict_color),
                ("FONTNAME", (1, 2), (1, 2), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(outcome_table)

    # ---- Summary & analysis (Claude-written narrative) ---------------------
    story.append(Paragraph("4. Summary &amp; Analysis", h2))
    story.append(Paragraph(f"<b>Executive summary:</b> {narrative['executive_summary']}", body))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Analysis:</b> {narrative['analysis']}", body))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"<b>Recommendation:</b> {narrative['recommendation']}", body))

    # ---- Test case execution details ---------------------------------------
    if step_rows:
        story.append(Paragraph("5. Test Case Execution Details", h2))
        case_rows = [["#", "Test Step", "Status", "Notes"]]
        for i, row in enumerate(step_rows, start=1):
            case_rows.append([str(i), Paragraph(row["step"], small), row["status"], Paragraph(row["note"], small)])
        case_table = Table(case_rows, colWidths=[20, 175, 55, 220])
        style_cmds = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]
        for i, row in enumerate(step_rows, start=1):
            color = _STEP_STATUS_COLORS.get(row["status"], colors.black)
            style_cmds.append(("TEXTCOLOR", (2, i), (2, i), color))
            style_cmds.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
        case_table.setStyle(TableStyle(style_cmds))
        story.append(case_table)

    # ---- Quality metrics -----------------------------------------------------
    if metrics:
        story.append(Paragraph("6. Quality Metrics", h2))
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

    # ---- Defects / findings ---------------------------------------------------
    findings = report.get("findings") or []
    if findings:
        story.append(Paragraph("7. Defects / Findings", h2))
        finding_rows = [["ID", "Severity", "Summary", "Error"]]
        for i, f in enumerate(findings, start=1):
            finding_rows.append(
                [
                    f"DEF-{i:03d}",
                    f["severity"].upper(),
                    Paragraph(f["summary"], small),
                    Paragraph(f.get("error_message") or "-", small),
                ]
            )
        finding_table = Table(finding_rows, colWidths=[45, 55, 210, 160])
        style_cmds = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]
        severity_colors = {"HIGH": _FAIL_COLOR, "MEDIUM": _WARN_COLOR, "LOW": _SKIP_COLOR}
        for i, f in enumerate(findings, start=1):
            color = severity_colors.get(f["severity"].upper())
            if color:
                style_cmds.append(("TEXTCOLOR", (1, i), (1, i), color))
                style_cmds.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
        finding_table.setStyle(TableStyle(style_cmds))
        story.append(finding_table)

    # ---- Stage timings ----------------------------------------------------
    if timings:
        story.append(Paragraph("8. Stage Timings", h2))
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

    # ---- Evidence / screenshots ---------------------------------------------
    action_entries = exploration.get("actions") or []
    screenshotted = [a for a in action_entries if a.get("screenshot_path")][:_MAX_REPORT_SCREENSHOTS]
    if screenshotted:
        story.append(Paragraph("9. Evidence — Action Screenshots", h2))
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
