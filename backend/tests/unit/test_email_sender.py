from unittest.mock import MagicMock, patch

import pytest

from app.agents.email_sender import EmailError, EmailSender


def test_send_raises_when_smtp_not_configured(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("ALERT_EMAIL_TO", raising=False)
    sender = EmailSender()

    with pytest.raises(EmailError, match="SMTP_HOST and ALERT_EMAIL_TO"):
        sender.send("subject", "body")


def test_send_success_calls_smtp_correctly(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "bot@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("ALERT_EMAIL_TO", "dua@example.com")
    sender = EmailSender()

    mock_server = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        sender.send("High severity finding", "Login is broken.")

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("bot@example.com", "app-password")
    mock_server.send_message.assert_called_once()
    sent_message = mock_server.send_message.call_args.args[0]
    assert sent_message["Subject"] == "High severity finding"
    assert sent_message["To"] == "dua@example.com"


def test_send_wraps_smtp_exceptions(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "dua@example.com")
    sender = EmailSender()

    with patch("smtplib.SMTP", side_effect=OSError("connection refused")):
        with pytest.raises(EmailError, match="Failed to send alert email"):
            sender.send("subject", "body")
