"""Anthropic adapter (Messages API via the official SDK).

Thinking is left at the model default (adaptive); depth is controlled with `effort`. For
models that support it, server-side refusal fallback (`fallbacks="default"`) is enabled so a
policy decline is retried on a suitable model inside the same call.
"""

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from kehora_llm.errors import FatalLLMError, RefusalError, RetryableLLMError
from kehora_llm.types import (
    Completion,
    LLMRequest,
    Message,
    StreamDone,
    StreamEvent,
    TextDelta,
    ToolCall,
    Usage,
)

SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"
SERVER_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"}


def _content(message: Message) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in message.content:
        if part.type == "text":
            blocks.append({"type": "text", "text": part.text})
        else:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": part.media_type,
                        "data": part.data_b64,
                    },
                }
            )
    return blocks


def build_params(model: str, request: LLMRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": request.max_tokens,
        "messages": [{"role": m.role, "content": _content(m)} for m in request.messages],
    }
    if request.system:
        params["system"] = request.system
    output_config: dict[str, Any] = {}
    if request.effort:
        output_config["effort"] = request.effort
    if request.output_schema is not None:
        output_config["format"] = {
            "type": "json_schema",
            "schema": anthropic.transform_schema(request.output_schema),
        }
    if output_config:
        params["output_config"] = output_config
    if request.tools:
        # Forced tool_choice is rejected on current models; `auto` + the prompt steers.
        params["tools"] = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": anthropic.transform_schema(t.input_schema),
            }
            for t in request.tools
        ]
    if model in SERVER_FALLBACK_MODELS:
        params["betas"] = [SERVER_FALLBACK_BETA]
        params["fallbacks"] = "default"
    return params


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, anthropic.APIConnectionError):  # includes APITimeoutError
        return RetryableLLMError(f"anthropic: {exc}")
    if isinstance(exc, anthropic.RateLimitError):
        return RetryableLLMError(f"anthropic rate limited: {exc.message}")
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code >= 500 or exc.status_code == 529:
            return RetryableLLMError(f"anthropic {exc.status_code}: {exc.message}")
        return FatalLLMError(f"anthropic {exc.status_code}: {exc.message}")
    return exc


def to_completion(message: Any) -> Completion:
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise RefusalError(
            getattr(details, "explanation", None) or "request declined",
            getattr(details, "category", None),
        )
    texts: list[str] = []
    calls: list[ToolCall] = []
    for block in message.content:
        if block.type == "text":
            texts.append(block.text)
        elif block.type == "tool_use":
            calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))
    u = message.usage
    return Completion(
        provider="anthropic",
        model=message.model,
        text="".join(texts),
        tool_calls=calls,
        stop_reason=message.stop_reason,
        usage=Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", None) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", None) or 0,
        ),
    )


class AnthropicAdapter:
    provider = "anthropic"

    def __init__(
        self,
        api_key: str,
        timeout: float = 600.0,
        max_retries: int = 2,
        http_client: Any = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=max_retries, http_client=http_client
        )

    async def complete(self, model: str, request: LLMRequest) -> Completion:
        try:
            message = await self._client.beta.messages.create(**build_params(model, request))
        except anthropic.AnthropicError as exc:
            raise _translate(exc) from exc
        return to_completion(message)

    async def stream(self, model: str, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        try:
            async with self._client.beta.messages.stream(**build_params(model, request)) as s:
                async for text in s.text_stream:
                    yield TextDelta(text=text)
                final = await s.get_final_message()
        except anthropic.AnthropicError as exc:
            raise _translate(exc) from exc
        yield StreamDone(completion=to_completion(final))
