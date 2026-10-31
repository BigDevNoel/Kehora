"""Gemini adapter against a mocked HTTP transport: real SDK request bodies, no network."""

import base64
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from kehora_llm.adapters.gemini_adapter import GeminiAdapter
from kehora_llm.errors import FatalLLMError, RefusalError, RetryableLLMError
from kehora_llm.types import ImagePart, LLMRequest, Message, StreamDone, TextDelta, ToolSpec

Handler = Callable[[httpx.Request], httpx.Response]
PNG = base64.b64encode(b"\x89PNG fake").decode()


def _adapter(handler: Handler) -> GeminiAdapter:
    return GeminiAdapter(
        "test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


def _response(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {"text": "thinking out loud", "thought": True},
                        {"text": '{"ok": true}'},
                    ],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 120,
            "cachedContentTokenCount": 20,
            "candidatesTokenCount": 30,
            "thoughtsTokenCount": 50,
        },
        "modelVersion": "gemini-4-argon-001",
    }
    body.update(overrides)
    return body


async def test_request_shape_and_response_mapping() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_response())

    request = LLMRequest(
        system="You are a test.",
        messages=[
            Message.user("Describe it", [ImagePart(media_type="image/png", data_b64=PNG)]),
            Message(role="assistant", content=[{"type": "text", "text": "Sure."}]),
        ],
        max_tokens=1234,
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        effort="xhigh",
    )
    completion = await _adapter(handler).complete("gemini-4-argon", request)

    assert seen["url"].endswith("/models/gemini-4-argon:generateContent")
    assert seen["key"] == "test-key"
    body = seen["body"]
    assert body["systemInstruction"]["parts"] == [{"text": "You are a test."}]
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    image, text = body["contents"][0]["parts"]
    assert image["inlineData"]["mime_type"] == "image/png" and text == {"text": "Describe it"}
    config = body["generationConfig"]
    assert config["maxOutputTokens"] == 1234
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"]["properties"]["ok"] == {"type": "boolean"}
    assert config["thinkingConfig"]["thinking_level"] == "HIGH"

    assert completion.text == '{"ok": true}'  # thought parts are dropped
    assert completion.model == "gemini-4-argon-001" and completion.stop_reason == "STOP"
    assert completion.usage.input_tokens == 100 and completion.usage.cache_read_tokens == 20
    assert completion.usage.output_tokens == 80  # thinking tokens are billed as output


async def test_tools_become_function_declarations_and_calls_map_back() -> None:
    seen: dict[str, Any] = {}
    call = {"functionCall": {"id": "c1", "name": "run_cad", "args": {"script": "result = 1"}}}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        candidate = {"content": {"role": "model", "parts": [call]}, "finishReason": "STOP"}
        return httpx.Response(200, json=_response(candidates=[candidate]))

    schema = {"type": "object", "properties": {"script": {"type": "string"}}}
    request = LLMRequest(
        messages=[Message.user("go")],
        tools=[ToolSpec(name="run_cad", description="Run a CAD script", input_schema=schema)],
    )
    completion = await _adapter(handler).complete("gemini-3.8-flash", request)
    [decl] = seen["body"]["tools"][0]["functionDeclarations"]
    assert decl["name"] == "run_cad" and decl["parameters_json_schema"] == schema
    assert "thinkingConfig" not in seen["body"].get("generationConfig", {})
    [tool_call] = completion.tool_calls
    assert (tool_call.id, tool_call.name, tool_call.input) == (
        "c1",
        "run_cad",
        {"script": "result = 1"},
    )


@pytest.mark.parametrize(
    "body",
    [
        {"promptFeedback": {"blockReason": "SAFETY"}, "candidates": []},
        {"candidates": [{"content": {"role": "model", "parts": []}, "finishReason": "SAFETY"}]},
    ],
)
async def test_blocked_prompts_and_answers_raise_refusal(body: dict[str, Any]) -> None:
    adapter = _adapter(lambda _: httpx.Response(200, json=body))
    with pytest.raises(RefusalError) as info:
        await adapter.complete("gemini-4-argon", LLMRequest(messages=[Message.user("hi")]))
    assert info.value.category == "SAFETY"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, FatalLLMError),
        (403, FatalLLMError),
        (429, RetryableLLMError),
        (503, RetryableLLMError),
    ],
)
async def test_error_mapping(status: int, expected: type[Exception]) -> None:
    error = {"error": {"code": status, "message": "nope", "status": "X"}}
    adapter = _adapter(lambda _: httpx.Response(status, json=error))
    with pytest.raises(expected, match=f"gemini {status}"):
        await adapter.complete("gemini-4-argon", LLMRequest(messages=[Message.user("hi")]))


async def test_connection_error_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(RetryableLLMError):
        await _adapter(handler).complete(
            "gemini-4-argon", LLMRequest(messages=[Message.user("hi")])
        )


async def test_stream_yields_deltas_then_done() -> None:
    chunks = [
        {"candidates": [{"content": {"role": "model", "parts": [{"text": "Hel"}]}}]},
        {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": "lo"}]}, "finishReason": "STOP"}
            ],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
            "modelVersion": "gemini-3.8-flash-001",
        },
    ]
    sse = "".join(f"data: {json.dumps(c)}\r\n\r\n" for c in chunks)

    def handler(request: httpx.Request) -> httpx.Response:
        assert ":streamGenerateContent" in str(request.url)
        return httpx.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )

    events = [
        e
        async for e in _adapter(handler).stream(
            "gemini-3.8-flash", LLMRequest(messages=[Message.user("hi")])
        )
    ]
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hel", "lo"]
    done = events[-1]
    assert isinstance(done, StreamDone)
    assert done.completion.text == "Hello" and done.completion.stop_reason == "STOP"
    assert done.completion.usage.output_tokens == 2
    assert done.completion.model == "gemini-3.8-flash-001"
