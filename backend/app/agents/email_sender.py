"""Thin wrapper around smtplib so the Reporter doesn't touch raw SMTP
itself, and so tests can substitute a fake sender without needing a real
mail server.
"""

import os
import smtplib
from email.message import EmailMessage


class EmailError(Exception):
    """Raised when an alert email can't be sent - missing config, or the
    SMTP server rejected/couldn't be reached."""


class EmailSender:
    def __init__(self) -> None:
        self._host = os.environ.get("SMTP_HOST", "")
        self._port = int(os.environ.get("SMTP_PORT", "587"))
        self._username = os.environ.get("SMTP_USERNAME", "")
        self._password = os.environ.get("SMTP_PASSWORD", "")
        self._from_addr = os.environ.get("ALERT_EMAIL_FROM", self._username)
        self._to_addr = os.environ.get("ALERT_EMAIL_TO", "")

    def send(self, subject: str, body: str) -> None:
        if not self._host or not self._to_addr:
            raise EmailError("SMTP_HOST and ALERT_EMAIL_TO must be set to send alert emails.")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._from_addr
        message["To"] = self._to_addr
        message.set_content(body)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as server:
                server.starttls()
                if self._username:
                    server.login(self._username, self._password)
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailError(f"Failed to send alert email: {exc}") from exc
