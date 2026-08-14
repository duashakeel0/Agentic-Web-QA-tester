"""Where a Trello API key/token get stored when set from the dashboard's
Trello Settings page, instead of requiring a backend .env file - closes
the gap a hosted, non-technical user would otherwise hit (no filesystem
access to edit .env). Deliberately the same lightweight local-file
pattern the domain manifest already uses (app/domains/manifest.py), just
gitignored here (backend/data/) since this file holds real secrets, not
shareable domain knowledge.

Single, shared connection by design - this app has one login, not
per-user accounts, so there's exactly one Trello connection slot at a
time; connecting a new one replaces whatever was there rather than
adding a second one alongside it.
"""

import json
import os
from pathlib import Path

SETTINGS_PATH = Path(os.environ.get("TRELLO_SETTINGS_PATH", "data/trello_settings.json"))


def load_trello_settings() -> dict | None:
    """Returns {"api_key": ..., "token": ...} if something's been saved
    from the dashboard, else None - callers fall back to TRELLO_API_KEY/
    TRELLO_TOKEN env vars in that case, so an existing .env-based setup
    keeps working completely unchanged for anyone who never touches the
    new settings page."""
    if not SETTINGS_PATH.exists():
        return None
    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    api_key, token = data.get("api_key"), data.get("token")
    if not api_key or not token:
        return None
    return {"api_key": api_key, "token": token}


def save_trello_settings(api_key: str, token: str) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps({"api_key": api_key, "token": token}))


def clear_trello_settings() -> None:
    """"Disconnect" - removes the stored connection. Falls back to
    TRELLO_API_KEY/TRELLO_TOKEN env vars afterward, same as if nothing
    had ever been saved from the dashboard at all."""
    SETTINGS_PATH.unlink(missing_ok=True)
