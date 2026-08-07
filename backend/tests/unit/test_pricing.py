from app.agents.pricing import estimate_cost_usd


def test_ollama_is_always_free():
    assert estimate_cost_usd("ollama", input_tokens=1_000_000, output_tokens=1_000_000) == 0.0


def test_claude_cost_uses_default_rates():
    cost = estimate_cost_usd("claude", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == 3.0 + 15.0


def test_claude_cost_scales_linearly():
    cost = estimate_cost_usd("claude", input_tokens=500_000, output_tokens=0)
    assert cost == 1.5


def test_zero_tokens_is_zero_cost():
    assert estimate_cost_usd("claude", input_tokens=0, output_tokens=0) == 0.0


def test_env_override_changes_rate(monkeypatch):
    monkeypatch.setenv("CLAUDE_INPUT_COST_PER_MTOK", "10")
    monkeypatch.setenv("CLAUDE_OUTPUT_COST_PER_MTOK", "20")
    cost = estimate_cost_usd("claude", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == 30.0
