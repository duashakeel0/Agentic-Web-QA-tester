from app.mcp_server.server import get_ticket, post_summary
from app.mcp_server.trello_client import TrelloError


async def test_get_ticket_returns_card_data(monkeypatch):
    class FakeClient:
        def __init__(self):
            pass

        async def get_card(self, card_id):
            return {"id": card_id, "title": "A ticket", "description": "desc", "checklist": []}

    monkeypatch.setattr("app.mcp_server.server.TrelloClient", FakeClient)

    result = await get_ticket("abc123")

    assert result["title"] == "A ticket"


async def test_get_ticket_wraps_trello_error_as_dict(monkeypatch):
    class FakeClient:
        async def get_card(self, card_id):
            raise TrelloError("No card found with ID 'abc123'.")

    monkeypatch.setattr("app.mcp_server.server.TrelloClient", FakeClient)

    result = await get_ticket("abc123")

    assert result == {"error": "No card found with ID 'abc123'."}


async def test_post_summary_returns_confirmation(monkeypatch):
    class FakeClient:
        async def add_comment(self, card_id, text):
            return {"posted": True, "comment_id": "c1"}

    monkeypatch.setattr("app.mcp_server.server.TrelloClient", FakeClient)

    result = await post_summary("abc123", "Test summary")

    assert result == {"posted": True, "comment_id": "c1"}


async def test_post_summary_wraps_trello_error_as_dict(monkeypatch):
    class FakeClient:
        async def add_comment(self, card_id, text):
            raise TrelloError("Trello is down.")

    monkeypatch.setattr("app.mcp_server.server.TrelloClient", FakeClient)

    result = await post_summary("abc123", "Test summary")

    assert result == {"error": "Trello is down."}
