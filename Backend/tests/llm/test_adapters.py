"""Adapters against mocked HTTP: request shape on the wire, response mapping, error mapping."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from kehora_llm.adapters.anthropic_adapter import AnthropicAdapter
from kehora_llm.adapters.openai_adapter import OpenAIAdapter
from kehora_llm.errors import FatalLLMError, RefusalError, RetryableLLMError
from kehora_llm.types import ImagePart, LLMRequest, Message, StreamDone, TextDelta, ToolSpec

Handler = Callable[[httpx2.Request], httpx2.Response]


def _client(handler: Handler) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def _anthropic_message(**overrides: Any) -> dict[str, Any]:
    body = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": '{"title": "Stand"}'},
            {"type": "tool_use", "id": "tu_1", "name": "run_cad", "input": {"script": "box()"}},
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_read_input_tokens": 5,
            "cache_creation_input_tokens": 0,
        },
    }
    body.update(overrides)
    return body


REQ = LLMRequest(
    system="You write specs.",
    messages=[
        Message.user("Make a stand", [ImagePart(media_type="image/png", data_b64="iVBORw0KGgo=")])
    ],
    tools=[
        ToolSpec(
            name="run_cad", description="Run CAD", input_schema={"type": "object", "properties": {}}
        )
    ],
    output_schema={"type": "object", "properties": {"title": {"type": "string", "minLength": 1}}},
    effort="high",
)


async def test_anthropic_request_shape_and_mapping() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["url"] = str(request.url)
        seen["beta"] = request.headers.get("anthropic-beta")
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_anthropic_message())

    adapter = AnthropicAdapter("sk-test", max_retries=0, http_client=_client(handler))
    out = await adapter.complete("claude-opus-5-5", REQ)

    body = seen["body"]
    assert seen["url"].endswith("/v1/messages")
    assert "server-side-fallback-2026-07-01" in seen["beta"]
    assert body["fallbacks"] == "default"
    assert body["system"] == "You write specs."
    assert body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in body and "tool_choice" not in body
    assert body["messages"][0]["content"][0]["source"]["media_type"] == "image/png"
    assert out.text == '{"title": "Stand"}'
    assert out.tool_calls[0].name == "run_cad" and out.tool_calls[0].input == {"script": "box()"}
    assert out.usage.input_tokens == 100 and out.usage.cache_read_tokens == 5


async def test_anthropic_haiku_has_no_server_fallback() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, json=_anthropic_message(model="claude-haiku-5-5"))

    adapter = AnthropicAdapter("sk-test", max_retries=0, http_client=_client(handler))
    await adapter.complete("claude-haiku-5-5", LLMRequest(messages=[Message.user("hi")]))
    assert "fallbacks" not in seen["body"]


async def test_anthropic_refusal_raises() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json=_anthropic_message(
                content=[],
                stop_reason="refusal",
                stop_details={"type": "refusal", "category": "cyber", "explanation": "no"},
            ),
        )

    adapter = AnthropicAdapter("sk-test", max_retries=0, http_client=_client(handler))
    with pytest.raises(RefusalError) as info:
        await adapter.complete("claude-opus-5-5", REQ)
    assert info.value.category == "cyber"


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, RetryableLLMError),
        (529, RetryableLLMError),
        (500, RetryableLLMError),
        (400, FatalLLMError),
        (401, FatalLLMError),
    ],
)
async def test_anthropic_error_mapping(status: int, expected: type[Exception]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status, json={"type": "error", "error": {"type": "x", "message": "boom"}}
        )

    adapter = AnthropicAdapter("sk-test", max_retries=0, http_client=_client(handler))
    with pytest.raises(expected):
        await adapter.complete("claude-opus-5-5", REQ)


async def test_anthropic_connection_error_is_retryable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("down", request=request)

    adapter = AnthropicAdapter("sk-test", max_retries=0, http_client=_client(handler))
    with pytest.raises(RetryableLLMError):
        await adapter.complete("claude-opus-5-5", REQ)


async def test_anthropic_stream() -> None:
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    **_anthropic_message(content=[]),
                    "usage": {"input_tokens": 7, "output_tokens": 1},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Hel"},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "lo"},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 2},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    sse = "".join(f"event: {e}\ndata: {json.dumps(d)}\n\n" for e, d in events)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    adapter = AnthropicAdapter("sk-test", max_retries=0, http_client=_client(handler))
    got = [
        e
        async for e in adapter.stream("claude-opus-5-5", LLMRequest(messages=[Message.user("hi")]))
    ]
    assert [e.text for e in got if isinstance(e, TextDelta)] == ["Hel", "lo"]
    done = got[-1]
    assert isinstance(done, StreamDone)
    assert done.completion.text == "Hello" and done.completion.usage.output_tokens == 2


async def test_openai_request_shape_and_mapping() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["body"] = json.loads(request.content)
        return httpx2.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-5.5",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"title": "Stand"}',
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "run_cad",
                                        "arguments": '{"script": "box()"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 9,
                    "total_tokens": 59,
                    "prompt_tokens_details": {"cached_tokens": 10},
                },
            },
        )

    adapter = OpenAIAdapter("sk-test", max_retries=0, http_client=_client(handler))
    out = await adapter.complete("gpt-5.5", REQ)
    body = seen["body"]
    assert body["messages"][0] == {"role": "system", "content": "You write specs."}
    assert body["messages"][1]["content"][0]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert body["response_format"]["type"] == "json_schema"
    assert body["tools"][0]["function"]["name"] == "run_cad"
    assert out.tool_calls[0].input == {"script": "box()"}
    assert out.usage.input_tokens == 40 and out.usage.cache_read_tokens == 10


@pytest.mark.parametrize(
    "status,expected", [(429, RetryableLLMError), (503, RetryableLLMError), (400, FatalLLMError)]
)
async def test_openai_error_mapping(status: int, expected: type[Exception]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": {"message": "boom", "type": "x"}})

    adapter = OpenAIAdapter("sk-test", max_retries=0, http_client=_client(handler))
    with pytest.raises(expected):
        await adapter.complete("gpt-5.5", REQ)
