from PIL import Image as PILImage

from app.history.schema import HistoryDetail
from app.pdf_report import _format_expected_outcome, _step_rows, build_pdf

_NARRATIVE = {
    "executive_summary": "Summary.",
    "analysis": "Analysis.",
    "recommendation": "Recommendation.",
}


def _entry(result: dict) -> HistoryDetail:
    return HistoryDetail(
        id=1,
        ticket_id="T1",
        domain="practice_software_testing",
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


def test_build_pdf_renders_a_realistic_full_report():
    # A comprehensive, realistic fixture (steps, expected outcome,
    # verification, metrics, findings, timings) - smoke-tests every new
    # report section together, not just that an empty/minimal run doesn't
    # crash the PDF builder.
    result = {
        "plan": {
            "ticket_title": "Verify Toolshop login",
            "steps": [
                "Navigate to the URL https://practicesoftwaretesting.com/auth/login",
                'Enter "customer@practicesoftwaretesting.com" into the Email field',
                'Enter "welcome01" into the Password field',
                "Click the Login button",
            ],
            "expected_outcome": {"url_contains": "/account", "text_contains": None},
        },
        "exploration": {
            "completed": True,
            "actions": [
                {
                    "step": 'Enter "customer@practicesoftwaretesting.com" into the Email field',
                    "action": "fill",
                    "selector": "#email",
                    "success": True,
                    "error": None,
                    "screenshot_path": None,
                },
                {
                    "step": 'Enter "welcome01" into the Password field',
                    "action": "fill",
                    "selector": "#password",
                    "success": True,
                    "error": None,
                    "screenshot_path": None,
                },
                {
                    "step": "Click the Login button",
                    "action": "click",
                    "selector": "#submit",
                    "success": True,
                    "error": None,
                    "screenshot_path": None,
                },
            ],
        },
        "verification": {
            "verdict": "pass",
            "initial_check_passed": True,
            "explanation": "The URL after login contains /account as expected.",
        },
        "metrics": {
            "steps_planned": 4,
            "steps_covered": 3,
            "coverage_ratio": 0.75,
            "actions_attempted": 3,
            "actions_succeeded": 3,
            "accuracy_ratio": 1.0,
            "llm_call_count": 5,
            "input_tokens": 1200,
            "output_tokens": 300,
        },
        "report": {
            "findings": [
                {"severity": "low", "summary": "Minor delay observed.", "error_message": None},
            ]
        },
        "timings": [
            {"agent": "planner", "model": "llama-3.1-8b-instant", "started_at": 0.0, "finished_at": 1.0, "duration_ms": 1000.0},
        ],
    }

    pdf_bytes = build_pdf(_entry(result), _NARRATIVE)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_format_expected_outcome_combines_both_fields():
    text = _format_expected_outcome({"url_contains": "/account", "text_contains": "Welcome"})
    assert "/account" in text
    assert "Welcome" in text


def test_format_expected_outcome_handles_none():
    assert _format_expected_outcome(None) == "n/a"
    assert _format_expected_outcome({}) == "n/a"


def test_step_rows_marks_pass_fail_skip_and_not_reached():
    plan = {
        "steps": ["Navigate to the homepage", "Fill the form", "Submit the form", "Confirm success"],
    }
    exploration = {
        "completed": False,
        "actions": [
            # No actions at all for "Navigate to the homepage" - and the
            # run did complete up to a point, but not all the way, so this
            # should read as skipped only if the whole run completed -
            # here it didn't, so a step with zero actions further down
            # should read "not reached" instead.
            {"step": "Fill the form", "action": "fill", "selector": "#x", "success": True, "is_broken_input_attempt": False},
            {
                "step": "Submit the form",
                "action": "click",
                "selector": "#submit",
                "success": False,
                "error": "Timed out",
                "is_broken_input_attempt": False,
            },
        ],
    }

    rows = _step_rows(plan, exploration)

    assert rows[0]["status"] == "NOT REACHED"  # no actions, run didn't complete
    assert rows[1]["status"] == "PASS"
    assert rows[2]["status"] == "FAIL"
    assert "Timed out" in rows[2]["note"]
    assert rows[3]["status"] == "NOT REACHED"


def test_step_rows_marks_skipped_when_run_completed_with_no_actions_for_a_step():
    plan = {"steps": ["Navigate to the homepage", "Do something"]}
    exploration = {
        "completed": True,
        "actions": [
            {"step": "Do something", "action": "click", "selector": "#x", "success": True, "is_broken_input_attempt": False},
        ],
    }

    rows = _step_rows(plan, exploration)

    assert rows[0]["status"] == "SKIPPED"
    assert rows[1]["status"] == "PASS"


def test_step_rows_excludes_broken_input_probes():
    plan = {"steps": ["Fill the form"]}
    exploration = {
        "completed": True,
        "actions": [
            {
                "step": "Fill the form",
                "action": "fill",
                "selector": "#x",
                "success": False,
                "error": "invalid",
                "is_broken_input_attempt": True,
            },
        ],
    }

    rows = _step_rows(plan, exploration)

    # The only action recorded is a deliberate broken-input probe, not a
    # real attempt at the step - should read as skipped (run completed,
    # nothing real happened here), not as a failure.
    assert rows[0]["status"] == "SKIPPED"


def test_step_rows_passes_a_step_that_succeeded_before_a_later_unrelated_hiccup():
    # Reproduces a real ParaBank report: the transfer's submit click
    # actually succeeded, but the loop queried the model again (the
    # confirmation hadn't rendered in that snapshot yet), and that second,
    # redundant decision hit an unrelated LLM parsing error - recorded as
    # the step's *last* action even though the step's real goal was
    # already achieved by the first one. The step genuinely passed and
    # must not read FAIL just because its last logged attempt was noise.
    plan = {"steps": ["Submit the transfer"]}
    exploration = {
        "completed": True,
        "actions": [
            {
                "step": "Submit the transfer", "action": "click", "selector": "input[type='submit']",
                "success": True, "is_broken_input_attempt": False,
            },
            {
                "step": "Submit the transfer", "action": "unknown", "selector": None,
                "success": False, "error": "claude returned an unparseable response", "is_broken_input_attempt": False,
            },
        ],
    }

    rows = _step_rows(plan, exploration)

    assert rows[0]["status"] == "PASS"
    assert "2 action(s)" in rows[0]["note"]
