import httpx
import pytest

from app.mcp_server.trello_client import TrelloClient, TrelloError, verify_trello_credentials


@pytest.fixture(autouse=True)
def trello_credentials(monkeypatch):
    monkeypatch.setenv("TRELLO_API_KEY", "fake-key")
    monkeypatch.setenv("TRELLO_TOKEN", "fake-token")


def test_constructor_requires_credentials(monkeypatch):
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    with pytest.raises(TrelloError, match="TRELLO_API_KEY"):
        TrelloClient()


async def test_get_card_returns_structured_data(httpx_mock):
    httpx_mock.add_response(
        json={
            "id": "abc123",
            "name": "Verify login works",
            "desc": "Check that a valid login redirects to the dashboard.",
            "checklists": [{"checkItems": [{"name": "Test happy path", "state": "complete"}]}],
        }
    )
    client = TrelloClient()

    card = await client.get_card("abc123")

    assert card["title"] == "Verify login works"
    assert card["checklist"] == [{"name": "Test happy path", "checked": True}]


async def test_get_card_404_raises_not_found_error(httpx_mock):
    httpx_mock.add_response(status_code=404)
    client = TrelloClient()

    with pytest.raises(TrelloError, match="No card found"):
        await client.get_card("missing-id")


async def test_get_card_401_raises_auth_error(httpx_mock):
    httpx_mock.add_response(status_code=401)
    client = TrelloClient()

    with pytest.raises(TrelloError, match="rejected the API key"):
        await client.get_card("abc123")


async def test_get_card_network_error_raises_trelloerror(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("no route to host"))
    client = TrelloClient()

    with pytest.raises(TrelloError, match="Could not reach Trello"):
        await client.get_card("abc123")


async def test_add_comment_returns_posted_confirmation(httpx_mock):
    httpx_mock.add_response(json={"id": "comment-1"})
    client = TrelloClient()

    result = await client.add_comment("abc123", "Test summary text")

    assert result == {"posted": True, "comment_id": "comment-1"}


async def test_add_comment_404_raises_not_found_error(httpx_mock):
    httpx_mock.add_response(status_code=404)
    client = TrelloClient()

    with pytest.raises(TrelloError, match="cannot post a comment"):
        await client.add_comment("missing-id", "text")


async def test_verify_trello_credentials_succeeds_silently_for_working_credentials(httpx_mock):
    httpx_mock.add_response(json={"id": "member-1"})

    await verify_trello_credentials("real-key", "real-token")


async def test_verify_trello_credentials_rejects_credentials_trello_itself_rejects(httpx_mock):
    httpx_mock.add_response(status_code=401)

    with pytest.raises(TrelloError, match="rejected this API key/token"):
        await verify_trello_credentials("admin", "admin123")


async def test_verify_trello_credentials_raises_on_network_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("no route to host"))

    with pytest.raises(TrelloError, match="Could not reach Trello"):
        await verify_trello_credentials("real-key", "real-token")
