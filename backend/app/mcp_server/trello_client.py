"""Thin wrapper around the Trello REST API - the only place in the project
that knows Trello's actual URL shapes and field names. The MCP server calls
this; nothing else should call Trello directly.
"""

import os

import httpx

TRELLO_BASE_URL = "https://api.trello.com/1"


class TrelloError(Exception):
    """Raised for any Trello-specific failure, with a message specific
    enough to act on (per the tool-design rule: no generic failures)."""


class TrelloClient:
    def __init__(self) -> None:
        self.api_key = os.environ.get("TRELLO_API_KEY")
        self.token = os.environ.get("TRELLO_TOKEN")
        if not self.api_key or not self.token:
            raise TrelloError(
                "TRELLO_API_KEY and TRELLO_TOKEN must be set as environment "
                "variables before the Trello MCP server can be used."
            )

    def _auth_params(self) -> dict:
        return {"key": self.api_key, "token": self.token}

    async def get_card(self, card_id: str) -> dict:
        """Fetches a card's title, description, and checklist items."""
        params = {**self._auth_params(), "checklists": "all", "fields": "name,desc"}
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TRELLO_BASE_URL}/cards/{card_id}", params=params)

        if response.status_code == 404:
            raise TrelloError(f"No card found with ID '{card_id}' on this board.")
        if response.status_code == 401:
            raise TrelloError("Trello rejected the API key/token - check they're valid and not expired.")
        response.raise_for_status()

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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TRELLO_BASE_URL}/cards/{card_id}/actions/comments", params=params
            )

        if response.status_code == 404:
            raise TrelloError(f"No card found with ID '{card_id}' - cannot post a comment to it.")
        if response.status_code == 401:
            raise TrelloError("Trello rejected the API key/token - check they're valid and not expired.")
        response.raise_for_status()

        data = response.json()
        return {"posted": True, "comment_id": data["id"]}
