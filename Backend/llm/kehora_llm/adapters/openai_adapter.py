"""OpenAI adapter (Chat Completions via the official SDK). Used as the fallback provider."""

import json
from collections.abc import AsyncIterator
from typing import Any

import openai

from kehora_llm.errors import FatalLLMError, RefusalError, RetryableLLMError
from kehora_llm.types import (
    Completion,
    LLMRequest,
    StreamDone,
    StreamEvent,
    TextDelta,
    ToolCall,
    Usage,
)


def build_params(model: str, request: LLMRequest) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    for m in request.messages:
        parts: list[dict[str, Any]] = []
        for p in m.content:
            if p.type == "text":
                parts.append({"type": "text", "text": p.text})
            else:
                url = f"data:{p.media_type};base64,{p.data_b64}"
                parts.append({"type": "image_url", "image_url": {"url": url}})
        messages.append({"role": m.role, "content": parts})
    params: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": request.max_tokens,
    }
    if request.output_schema is not None:
        params["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": str(request.output_schema.get("title") or "output"),
                "schema": request.output_schema,
                "strict": False,
            },
        }
    if request.tools:
        params["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in request.tools
        ]
    return params


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, openai.APIConnectionError):  # includes APITimeoutError
        return RetryableLLMError(f"openai: {exc}")
    if isinstance(exc, openai.RateLimitError):
        return RetryableLLMError(f"openai rate limited: {exc.message}")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500:
            return RetryableLLMError(f"openai {exc.status_code}: {exc.message}")
        return FatalLLMError(f"openai {exc.status_code}: {exc.message}")
    return exc


def _usage(u: Any) -> Usage:
    if u is None:
        return Usage()
    details = getattr(u, "prompt_tokens_details", None)
    cached = (getattr(details, "cached_tokens", None) or 0) if details else 0
    return Usage(
        input_tokens=(u.prompt_tokens or 0) - cached,
        output_tokens=u.completion_tokens or 0,
        cache_read_tokens=cached,
    )


class OpenAIAdapter:
    provider = "openai"

    def __init__(
        self,
        api_key: str,
        timeout: float = 600.0,
        max_retries: int = 2,
        http_client: Any = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(
            api_key=api_key, timeout=timeout, max_retries=max_retries, http_client=http_client
        )

    async def complete(self, model: str, request: LLMRequest) -> Completion:
        try:
            resp = await self._client.chat.completions.create(**build_params(model, request))
        except openai.OpenAIError as exc:
            raise _translate(exc) from exc
        choice = resp.choices[0]
        msg = choice.message
        if getattr(msg, "refusal", None):
            raise RefusalError(str(msg.refusal))
        calls = [
            ToolCall(id=c.id, name=c.function.name, input=json.loads(c.function.arguments or "{}"))
            for c in (msg.tool_calls or [])
            if c.type == "function"
        ]
        return Completion(
            provider=self.provider,
            model=resp.model,
            text=msg.content or "",
            tool_calls=calls,
            stop_reason=choice.finish_reason,
            usage=_usage(resp.usage),
        )

    async def stream(self, model: str, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        params = {**build_params(model, request), "stream": True}
        params["stream_options"] = {"include_usage": True}
        texts: list[str] = []
        usage = Usage()
        served = model
        finish: str | None = None
        try:
            chunks = await self._client.chat.completions.create(**params)
            async for chunk in chunks:
                served = chunk.model or served
                if chunk.usage is not None:
                    usage = _usage(chunk.usage)
                for choice in chunk.choices:
                    finish = choice.finish_reason or finish
                    if choice.delta.content:
                        texts.append(choice.delta.content)
                        yield TextDelta(text=choice.delta.content)
        except openai.OpenAIError as exc:
            raise _translate(exc) from exc
        yield StreamDone(
            completion=Completion(
                provider=self.provider,
                model=served,
                text="".join(texts),
                stop_reason=finish,
                usage=usage,
            )
        )
