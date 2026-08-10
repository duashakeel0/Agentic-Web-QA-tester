import app.main as main_module
from app.agents.schema import AskContext, AskResult


class _FakeExplorer:
    """Records what it was constructed/called with so a test can assert
    the endpoint wired the request through correctly, and returns a
    canned AskResult instead of touching a real browser/LLM - the real
    ExplorerAgent.ask() path itself is covered by
    tests/unit/test_explorer_ask.py and the e2e file."""

    instances: list["_FakeExplorer"] = []

    def __init__(self, llm=None, on_action=None):
        self.llm = llm
        self.on_action = on_action
        self.ask_calls: list[tuple[str, AskContext | None]] = []
        _FakeExplorer.instances.append(self)

    async def ask(self, question, existing_context=None, close_browser=True):
        self.ask_calls.append((question, existing_context))
        if self.on_action is not None:
            await self.on_action(
                {
                    "kind": "action", "step": "(ask)", "action": "click", "selector": "#menu",
                    "value": None, "success": True, "error": None, "screenshot_url": None,
                    "target_box": None, "viewport": None, "is_broken_input_attempt": False,
                }
            )
        return AskResult(
            question=question, matched=True, domain="my_site", answer="The site sells widgets.",
            source="live_explore", final_url="https://my_site.example/products",
        )


def _reset(monkeypatch):
    _FakeExplorer.instances = []
    monkeypatch.setattr(main_module, "ExplorerAgent", _FakeExplorer)
    monkeypatch.setattr(main_module, "make_llm", lambda provider: object())


def test_ask_site_requires_auth(client):
    try:
        with client.websocket_connect("/ws/ask-site") as ws:
            ws.send_json({"question": "What does this site sell?"})
            ws.receive_json()
        rejected = False
    except Exception:
        rejected = True
    assert rejected


def test_ask_site_requires_a_question(client, auth_token):
    with client.websocket_connect(f"/ws/ask-site?token={auth_token}") as ws:
        ws.send_json({"question": "   "})
        event = ws.receive_json()
    assert event["type"] == "error"
    assert "question" in event["message"].lower()


def test_ask_site_rejects_an_unknown_provider(client, auth_token):
    with client.websocket_connect(f"/ws/ask-site?token={auth_token}") as ws:
        ws.send_json({"question": "What does this site sell?", "provider": "gpt4"})
        event = ws.receive_json()
    assert event["type"] == "error"
    assert "gpt4" in event["message"]


def test_ask_site_declines_an_unrecognized_domain(client, auth_token, monkeypatch):
    _reset(monkeypatch)

    class _DecliningExplorer(_FakeExplorer):
        async def ask(self, question, existing_context=None, close_browser=True):
            return AskResult(question=question, matched=False, reason="No registered domain concerns pizza delivery.")

    monkeypatch.setattr(main_module, "ExplorerAgent", _DecliningExplorer)

    with client.websocket_connect(f"/ws/ask-site?token={auth_token}") as ws:
        ws.send_json({"question": "Does this site deliver pizza?"})
        events = [ws.receive_json() for _ in range(2)]

    assert events[0]["type"] == "status"
    assert events[1]["type"] == "declined"
    assert "pizza" in events[1]["reason"]


def test_ask_site_streams_live_actions_then_the_answer(client, auth_token, monkeypatch):
    _reset(monkeypatch)

    with client.websocket_connect(f"/ws/ask-site?token={auth_token}") as ws:
        ws.send_json({"question": "What does this site sell?"})
        events = [ws.receive_json() for _ in range(3)]

    assert [e["type"] for e in events] == ["status", "action", "answer"]
    assert events[1]["step"] == "(ask)"
    assert "kind" not in events[1]  # forwarded as the event's own "type", same as /ws/pipeline
    assert events[2]["domain"] == "my_site"
    assert events[2]["answer"] == "The site sells widgets."
    assert events[2]["source"] == "live_explore"


def test_ask_site_passes_the_provided_context_through_to_the_explorer(client, auth_token, monkeypatch):
    _reset(monkeypatch)

    with client.websocket_connect(f"/ws/ask-site?token={auth_token}") as ws:
        ws.send_json(
            {
                "question": "What did the last run find?",
                "context": {
                    "domain": "my_site",
                    "final_url": "https://my_site.example/cart",
                    "final_page_text": "Your cart has 2 items.",
                    "actions": [
                        {"step": "Add to cart", "action": "click", "selector": "#add", "success": True},
                    ],
                },
            }
        )
        [ws.receive_json() for _ in range(3)]  # status, action, answer

    explorer = _FakeExplorer.instances[0]
    assert len(explorer.ask_calls) == 1
    question, context = explorer.ask_calls[0]
    assert question == "What did the last run find?"
    assert isinstance(context, AskContext)
    assert context.domain == "my_site"
    assert context.final_page_text == "Your cart has 2 items."
    assert context.actions[0].action == "click"


def test_ask_site_ignores_a_malformed_context_instead_of_failing(client, auth_token, monkeypatch):
    _reset(monkeypatch)

    with client.websocket_connect(f"/ws/ask-site?token={auth_token}") as ws:
        ws.send_json({"question": "What does this site sell?", "context": {"not_a_real_field": True}})
        events = [ws.receive_json() for _ in range(3)]

    assert events[-1]["type"] == "answer"
    explorer = _FakeExplorer.instances[0]
    assert explorer.ask_calls[0][1] is None
