"""Google Gemini adapter (Gemini Developer API via the official google-genai SDK).

Structured output uses `response_json_schema`; tools are function declarations. `effort` maps to
Gemini's `thinking_level` (low/medium -> LOW/MEDIUM, high and above -> HIGH).
"""

import base64
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import errors, types

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

THINKING_LEVELS = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
    "xhigh": types.ThinkingLevel.HIGH,
    "max": types.ThinkingLevel.HIGH,
}
REFUSAL_FINISH = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"}


def build_contents(request: LLMRequest) -> list[types.Content]:
    contents = []
    for m in request.messages:
        parts: list[types.Part] = []
        for p in m.content:
            if p.type == "text":
                parts.append(types.Part(text=p.text))
            else:
                data = base64.b64decode(p.data_b64)
                parts.append(types.Part.from_bytes(data=data, mime_type=p.media_type))
        contents.append(
            types.Content(role="model" if m.role == "assistant" else "user", parts=parts)
        )
    return contents


def build_config(request: LLMRequest) -> types.GenerateContentConfig:
    config = types.GenerateContentConfig(
        system_instruction=request.system,
        max_output_tokens=request.max_tokens,
    )
    if request.output_schema is not None:
        config.response_mime_type = "application/json"
        config.response_json_schema = request.output_schema
    if request.tools:
        config.tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t.name,
                        description=t.description,
                        parameters_json_schema=t.input_schema,
                    )
                    for t in request.tools
                ]
            )
        ]
    if request.effort:
        config.thinking_config = types.ThinkingConfig(
            thinking_level=THINKING_LEVELS[request.effort]
        )
    return config


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, errors.APIError):
        if exc.code == 429 or exc.code >= 500:
            return RetryableLLMError(f"gemini {exc.code}: {exc.message}")
        return FatalLLMError(f"gemini {exc.code}: {exc.message}")
    if isinstance(exc, (TimeoutError, ConnectionError)) or type(exc).__module__.startswith("httpx"):
        return RetryableLLMError(f"gemini: {exc}")
    return exc


def _usage(meta: Any) -> Usage:
    if meta is None:
        return Usage()
    cached = meta.cached_content_token_count or 0
    return Usage(
        input_tokens=(meta.prompt_token_count or 0) - cached,
        # Thinking tokens are billed as output.
        output_tokens=(meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0),
        cache_read_tokens=cached,
    )


def _finish(resp: types.GenerateContentResponse) -> str | None:
    if not resp.candidates or resp.candidates[0].finish_reason is None:
        return None
    return str(resp.candidates[0].finish_reason.name)


def _check_refusal(resp: types.GenerateContentResponse) -> None:
    feedback = resp.prompt_feedback
    if feedback is not None and feedback.block_reason is not None:
        raise RefusalError(
            feedback.block_reason_message or f"prompt blocked: {feedback.block_reason.name}",
            category=feedback.block_reason.name,
        )
    finish = _finish(resp)
    if finish in REFUSAL_FINISH:
        raise RefusalError(f"response blocked: {finish}", category=finish)


def _text(resp: types.GenerateContentResponse) -> str:
    """Answer text only: thought summaries are never part of the output."""
    if not resp.candidates or resp.candidates[0].content is None:
        return ""
    parts = resp.candidates[0].content.parts or []
    return "".join(p.text for p in parts if p.text and not p.thought)


class GeminiAdapter:
    provider = "gemini"

    def __init__(
        self,
        api_key: str,
        timeout: float = 600.0,
        max_retries: int = 4,
        retry_delay: float = 2.0,
        http_client: Any = None,
    ) -> None:
        # Gemini returns 503 "high demand" in bursts: retry the same model with backoff before
        # the gateway falls back to another provider (the other adapters' SDKs do the same).
        retry = types.HttpRetryOptions(
            attempts=max_retries + 1,
            initial_delay=retry_delay,
            max_delay=30.0,
            http_status_codes=[429, 500, 502, 503, 504],
        )
        options = types.HttpOptions(
            timeout=int(timeout * 1000), httpx_async_client=http_client, retry_options=retry
        )
        self._client = genai.Client(api_key=api_key, http_options=options)

    async def complete(self, model: str, request: LLMRequest) -> Completion:
        try:
            resp = await self._client.aio.models.generate_content(
                model=model, contents=build_contents(request), config=build_config(request)
            )
        except Exception as exc:
            raise _translate(exc) from exc
        _check_refusal(resp)
        calls = [
            ToolCall(id=c.id or f"call_{i}", name=c.name or "", input=dict(c.args or {}))
            for i, c in enumerate(resp.function_calls or [])
        ]
        return Completion(
            provider=self.provider,
            model=resp.model_version or model,
            text=_text(resp),
            tool_calls=calls,
            stop_reason=_finish(resp),
            usage=_usage(resp.usage_metadata),
        )

    async def stream(self, model: str, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        texts: list[str] = []
        usage = Usage()
        served = model
        finish: str | None = None
        try:
            chunks = await self._client.aio.models.generate_content_stream(
                model=model, contents=build_contents(request), config=build_config(request)
            )
            async for chunk in chunks:
                _check_refusal(chunk)
                served = chunk.model_version or served
                if chunk.usage_metadata is not None:
                    usage = _usage(chunk.usage_metadata)
                finish = _finish(chunk) or finish
                if text := _text(chunk):
                    texts.append(text)
                    yield TextDelta(text=text)
        except RefusalError:
            raise
        except Exception as exc:
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
