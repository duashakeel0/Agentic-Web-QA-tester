import pytest

from app.agents.reporter import ReporterAgent
from app.agents.schema import ActionLogEntry, ExplorationResult, RunResult, VerifierResult
from tests.helpers import FakeLLM


@pytest.fixture
def reporter():
    return ReporterAgent(llm=FakeLLM())


def _passing_run(domain="practice_software_testing", workflow="login"):
    exploration = ExplorationResult(
        ticket_id="T1", domain=domain, workflow=workflow, completed=True,
        actions=[ActionLogEntry(step="Log in", action="click", success=True)],
        final_url="https://x/inventory.html", final_page_text="Products",
    )
    verification = VerifierResult(
        ticket_id="T1", domain=domain, workflow=workflow, verdict="pass",
        assertion_checked={}, initial_check_passed=True, retried=False,
    )
    return RunResult(exploration=exploration, verification=verification)


def _failing_run(domain="practice_software_testing", workflow="login"):
    exploration = ExplorationResult(
        ticket_id="T1", domain=domain, workflow=workflow, completed=True,
        actions=[
            ActionLogEntry(step="Log in", action="click", selector="#login-btn", success=True),
            ActionLogEntry(
                step="Log in", action="fill", selector="#password", value="x", success=False,
                error="Timed out waiting for '#password'",
            ),
        ],
        final_url="https://x/login", final_page_text="Invalid credentials",
    )
    verification = VerifierResult(
        ticket_id="T1", domain=domain, workflow=workflow, verdict="fail",
        assertion_checked={"url_contains": "/inventory.html"}, initial_check_passed=False, retried=True,
        retry_passed=False, retry_error="Re-check navigation timed out.",
        explanation="Login never redirected to the dashboard.",
    )
    return RunResult(exploration=exploration, verification=verification)


def _pass_with_issues_run(domain="practice_software_testing", workflow="login", warning_count=1):
    exploration = ExplorationResult(
        ticket_id="T1", domain=domain, workflow=workflow, completed=True,
        actions=[
            ActionLogEntry(step="Log in", action="fill", selector="#u", success=False, error="timed out"),
            ActionLogEntry(step="Log in", action="click", success=True),
        ],
        final_url="https://x/inventory.html", final_page_text="Products",
    )
    verification = VerifierResult(
        ticket_id="T1", domain=domain, workflow=workflow, verdict="pass_with_issues", warning_count=warning_count,
        assertion_checked={}, initial_check_passed=True, retried=False,
    )
    return RunResult(exploration=exploration, verification=verification)


async def test_report_generates_low_severity_finding_for_pass_with_issues(reporter, monkeypatch):
    async def fake_post_summary(ticket_id, summary_text):
        return {"ok": True}

    monkeypatch.setattr("app.agents.reporter.post_summary", fake_post_summary)

    report = await reporter.report("T1", [_pass_with_issues_run()])

    assert len(report.findings) == 1
    assert report.findings[0].severity == "low"
    assert "1 action(s)" in report.findings[0].summary
    # No LLM call needed to classify a passing run - only the queued
    # post_summary response should have been consumed.
    assert len(reporter._llm.prompts) == 0


async def test_report_never_alerts_on_pass_with_issues(reporter, monkeypatch):
    sent_alerts = []

    class FakeEmailSender:
        def send(self, subject, body):
            sent_alerts.append(subject)

    async def fake_post_summary(ticket_id, summary_text):
        return {"ok": True}

    reporter._email_sender = FakeEmailSender()
    monkeypatch.setattr("app.agents.reporter.post_summary", fake_post_summary)

    await reporter.report("T1", [_pass_with_issues_run()])

    assert len(sent_alerts) == 0


def test_render_summary_pass_with_issues_not_counted_as_failed(reporter):
    from app.agents.schema import Report

    runs = [_pass_with_issues_run()]
    text = reporter._render_summary(Report(ticket_id="T1", findings=[]), runs)

    assert text.startswith("Result: PASS WITH ISSUES")
    assert "0 passed, 1 passed with issues, 0 failed out of 1 workflow(s)" in text
    assert "[PASS WITH ISSUES] practice_software_testing/login" in text
    assert "1 recovered error(s)" in text


async def test_classify_returns_severity_and_summary(reporter):
    reporter._llm.queue('{"severity": "high", "summary": "Login form rejects valid credentials."}')

    finding = await reporter._classify(_failing_run())

    assert finding.severity == "high"
    assert finding.summary == "Login form rejects valid credentials."
    assert finding.error_message == "Re-check navigation timed out."  # retry_error takes priority


async def test_classify_falls_back_to_exploration_error_when_no_retry_error(reporter):
    run = _failing_run()
    run.verification.retry_error = None
    run.exploration.error = "Explorer could not complete step 'Log in' within 6 actions."
    reporter._llm.queue('{"severity": "medium", "summary": "Login flow broken."}')

    finding = await reporter._classify(run)

    assert finding.error_message == "Explorer could not complete step 'Log in' within 6 actions."


async def test_classify_defaults_to_high_when_llm_unavailable():
    reporter = ReporterAgent(llm=None)
    reporter._llm = None

    finding = await reporter._classify(_failing_run())

    assert finding.severity == "high"
    assert "defaulting to high severity" in finding.summary


async def test_classify_defaults_to_high_on_bad_json(reporter):
    reporter._llm.queue("not json")

    finding = await reporter._classify(_failing_run())

    assert finding.severity == "high"
    assert "defaulting to high severity" in finding.summary


async def test_classify_defaults_to_high_on_invalid_severity_value(reporter):
    reporter._llm.queue('{"severity": "catastrophic", "summary": "whatever"}')

    finding = await reporter._classify(_failing_run())

    assert finding.severity == "high"


def test_render_summary_all_pass(reporter):
    from app.agents.schema import Report

    runs = [_passing_run()]
    text = reporter._render_summary(Report(ticket_id="T1", findings=[]), runs)

    assert text.startswith("Result: PASS")
    assert "1 passed, 0 passed with issues, 0 failed out of 1 workflow(s)" in text
    assert "[PASS] practice_software_testing/login" in text


async def test_render_summary_mixed_pass_fail(reporter):
    from app.agents.schema import Report

    fail_run = _failing_run()
    pass_run = _passing_run(workflow="checkout")
    reporter._llm.queue('{"severity": "high", "summary": "Login form rejects valid credentials."}')
    finding = await reporter._classify(fail_run)

    text = reporter._render_summary(Report(ticket_id="T1", findings=[finding]), [pass_run, fail_run])

    assert text.startswith("Result: FAIL")
    assert "1 passed, 0 passed with issues, 1 failed out of 2 workflow(s)" in text
    assert "[PASS] practice_software_testing/checkout" in text
    assert "Failure reason: Login form rejects valid credentials." in text
    assert "Error message: Re-check navigation timed out." in text
    assert "Reproduction steps:" in text


async def test_report_alerts_only_on_high_severity(reporter, monkeypatch):
    sent_alerts = []

    class FakeEmailSender:
        def send(self, subject, body):
            sent_alerts.append(subject)

    async def fake_post_summary(ticket_id, summary_text):
        return {"ok": True}

    reporter._email_sender = FakeEmailSender()
    monkeypatch.setattr("app.agents.reporter.post_summary", fake_post_summary)
    reporter._llm.queue('{"severity": "low", "summary": "Minor cosmetic issue."}')

    report = await reporter.report("T1", [_failing_run()])

    assert len(sent_alerts) == 0  # low severity - no alert
    assert report.post_summary_status == "posted"


async def test_report_posts_summary_with_retry_on_failure(reporter, monkeypatch):
    attempts = []

    async def flaky_post_summary(ticket_id, summary_text):
        attempts.append(1)
        if len(attempts) == 1:
            return {"error": "Trello API timeout"}
        return {"ok": True}

    monkeypatch.setattr("app.agents.reporter.post_summary", flaky_post_summary)

    report = await reporter.report("T1", [_passing_run()])

    assert len(attempts) == 2
    assert report.post_summary_status == "posted"


async def test_report_marks_failed_after_exhausting_retries(reporter, monkeypatch):
    async def always_fails(ticket_id, summary_text):
        return {"error": "Trello is down"}

    monkeypatch.setattr("app.agents.reporter.post_summary", always_fails)

    report = await reporter.report("T1", [_passing_run()])

    assert report.post_summary_status == "failed"
    assert report.post_summary_error == "Trello is down"
