import pytest

from app.agents.llm_client import LLMError
from tests.helpers import FakeLLM


async def test_complete_json_parses_valid_json():
    llm = FakeLLM(['{"a": 1, "b": "two"}'])
    data, response = await llm.complete_json("prompt")
    assert data == {"a": 1, "b": "two"}
    assert response.text == '{"a": 1, "b": "two"}'


async def test_complete_json_raises_llmerror_on_bad_json():
    llm = FakeLLM(["not json at all"])
    with pytest.raises(LLMError, match="unparseable"):
        await llm.complete_json("prompt")


async def test_complete_json_propagates_underlying_llmerror():
    llm = FakeLLM([LLMError("provider down")])
    with pytest.raises(LLMError, match="provider down"):
        await llm.complete_json("prompt")


async def test_usage_accumulates_across_calls():
    llm = FakeLLM(["1", "2", "3"])
    for _ in range(3):
        await llm.complete("prompt")
    assert llm.call_count == 3
    assert llm.total_input_tokens == 300
    assert llm.total_output_tokens == 60


async def test_usage_not_recorded_on_error():
    llm = FakeLLM([LLMError("boom")])
    with pytest.raises(LLMError):
        await llm.complete("prompt")
    assert llm.call_count == 0
    assert llm.total_input_tokens == 0
