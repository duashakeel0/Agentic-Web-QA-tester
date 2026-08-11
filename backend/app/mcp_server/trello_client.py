"""Thin wrapper around the Trello REST API - the only place in the project
that knows Trello's actual URL shapes and field names. The MCP server calls
this; nothing else should call Trello directly.
"""

import os

import httpx

from app.trello_settings import load_trello_settings

TRELLO_BASE_URL = "https://api.trello.com/1"


class TrelloError(Exception):
    """Raised for any Trello-specific failure, with a message specific
    enough to act on (per the tool-design rule: no generic failures).
    Never includes the request URL, since it carries the API key/token
    as query params."""


def _raise_for_status(response: httpx.Response, *, not_found_message: str) -> None:
    if response.status_code == 404:
        raise TrelloError(not_found_message)
    if response.status_code == 400:
        raise TrelloError("Trello rejected this ticket ID as invalid - it doesn't look like a real Trello card ID.")
    if response.status_code == 401:
        raise TrelloError("Trello rejected the API key/token - check they're valid and not expired.")
    if not response.is_success:
        raise TrelloError(f"Trello returned an unexpected error (status {response.status_code}).")


class TrelloClient:
    def __init__(self) -> None:
        # Credentials saved from the dashboard's Trello Settings page take
        # precedence - falls back to TRELLO_API_KEY/TRELLO_TOKEN env vars
        # so an existing .env-based setup keeps working unchanged for
        # anyone who never touches the settings page at all.
        stored = load_trello_settings()
        if stored is not None:
            self.api_key = stored["api_key"]
            self.token = stored["token"]
        else:
            self.api_key = os.environ.get("TRELLO_API_KEY")
            self.token = os.environ.get("TRELLO_TOKEN")
        if not self.api_key or not self.token:
            raise TrelloError(
                "Trello isn't connected yet - set it up from the dashboard's Trello Settings page, "
                "or set TRELLO_API_KEY and TRELLO_TOKEN as environment variables."
            )

    def _auth_params(self) -> dict:
        return {"key": self.api_key, "token": self.token}

    async def get_card(self, card_id: str) -> dict:
        """Fetches a card's title, description, and checklist items."""
        params = {**self._auth_params(), "checklists": "all", "fields": "name,desc"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{TRELLO_BASE_URL}/cards/{card_id}", params=params)
        except httpx.RequestError:
            raise TrelloError("Could not reach Trello - check your network connection and try again.")

        _raise_for_status(response, not_found_message=f"No card found with ID '{card_id}' on this board.")

        data = response.json()
        checklist_items = [
            {"name": item["name"], "checked": item["state"] == "complete"}
            for checklist in data.get("checklists", [])
            for item in checklist.get("checkItems", [])
        ]

        return {
            "id": data["id"],
            "title": data["name"],
            "description": data.get("desc", ""),
            "checklist": checklist_items,
        }

    async def add_comment(self, card_id: str, text: str) -> dict:
        """Posts a comment onto a card - used to write a run summary back."""
        params = {**self._auth_params(), "text": text}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{TRELLO_BASE_URL}/cards/{card_id}/actions/comments", params=params
                )
        except httpx.RequestError:
            raise TrelloError("Could not reach Trello - check your network connection and try again.")

        _raise_for_status(
            response, not_found_message=f"No card found with ID '{card_id}' - cannot post a comment to it."
        )

        data = response.json()
        return {"posted": True, "comment_id": data["id"]}
