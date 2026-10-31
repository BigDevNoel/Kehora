"""The model gateway: one interface (complete, stream, structured, tool_call, vision) for every
agent role, routed by config, with fallback across providers and per-call usage logging."""

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from kehora_common.logging import get_logger
from kehora_common.settings import Settings
from kehora_llm.adapters.base import ProviderAdapter
from kehora_llm.errors import FatalLLMError, OutputValidationError, RetryableLLMError
from kehora_llm.routing import ModelRef, PriceBook, RoutingTable
from kehora_llm.types import (
    Completion,
    Effort,
    ImagePart,
    LLMRequest,
    Message,
    StreamDone,
    StreamEvent,
    ToolSpec,
    UsageRecord,
)

log = get_logger(__name__)

UsageSink = Callable[[UsageRecord], Awaitable[None]]


async def _discard(_: UsageRecord) -> None:
    return None


class Gateway:
    def __init__(
        self,
        routing: RoutingTable,
        adapters: dict[str, ProviderAdapter],
        prices: PriceBook | None = None,
    ) -> None:
        self.routing = routing
        self.adapters = adapters
        self.prices = prices or PriceBook.load()

    # --- core ----------------------------------------------------------------------------
    def _candidates(self, role: str) -> list[tuple[ModelRef, ProviderAdapter]]:
        out = [
            (ref, self.adapters[ref.provider])
            for ref in self.routing.chain(role)
            if ref.provider in self.adapters
        ]
        if not out:
            raise FatalLLMError(f"no configured provider for role {role!r}")
        return out

    async def _record(
        self,
        sink: UsageSink,
        role: str,
        ref: ModelRef,
        completion: Completion,
        started: float,
        fallback_from: ModelRef | None,
    ) -> None:
        served = ModelRef(completion.provider, completion.model)
        cost = self.prices.cost_usd_micros(served, completion.usage)
        if cost is None:
            cost = self.prices.cost_usd_micros(ref, completion.usage)
        if cost is None:
            log.warning("llm_price_missing", model=str(served))
        await sink(
            UsageRecord(
                role=role,
                provider=completion.provider,
                model=completion.model,
                usage=completion.usage,
                cost_usd_micros=cost,
                latency_ms=int((time.monotonic() - started) * 1000),
                fallback_from=str(fallback_from) if fallback_from else None,
            )
        )

    async def complete(
        self, role: str, request: LLMRequest, on_usage: UsageSink = _discard
    ) -> Completion:
        last: Exception | None = None
        previous: ModelRef | None = None
        for ref, adapter in self._candidates(role):
            started = time.monotonic()
            try:
                completion = await adapter.complete(ref.model, request)
            except RetryableLLMError as exc:
                log.warning("llm_fallback", role=role, model=str(ref), error=str(exc))
                last, previous = exc, ref
                continue
            await self._record(on_usage, role, ref, completion, started, previous)
            return completion
        raise last or FatalLLMError("no candidates")

    async def stream(
        self, role: str, request: LLMRequest, on_usage: UsageSink = _discard
    ) -> AsyncIterator[StreamEvent]:
        """Falls back only if the failure happens before the first token is sent."""
        last: Exception | None = None
        previous: ModelRef | None = None
        for ref, adapter in self._candidates(role):
            started = time.monotonic()
            emitted = False
            try:
                async for event in adapter.stream(ref.model, request):
                    if isinstance(event, StreamDone):
                        await self._record(on_usage, role, ref, event.completion, started, previous)
                    emitted = True
                    yield event
                return
            except RetryableLLMError as exc:
                if emitted:
                    raise
                log.warning("llm_fallback", role=role, model=str(ref), error=str(exc))
                last, previous = exc, ref
        raise last or FatalLLMError("no candidates")

    # --- conveniences --------------------------------------------------------------------
    async def structured[M: BaseModel](
        self,
        role: str,
        output: type[M],
        messages: list[Message],
        *,
        system: str | None = None,
        effort: Effort | None = None,
        on_usage: UsageSink = _discard,
    ) -> M:
        schema = output.model_json_schema()
        completion = await self.complete(
            role,
            LLMRequest(system=system, messages=messages, output_schema=schema, effort=effort),
            on_usage,
        )
        try:
            return output.model_validate(json.loads(completion.text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise OutputValidationError(f"{output.__name__}: {exc}") from exc

    async def tool_call(
        self,
        role: str,
        messages: list[Message],
        tools: list[ToolSpec],
        *,
        system: str | None = None,
        on_usage: UsageSink = _discard,
    ) -> Completion:
        return await self.complete(
            role, LLMRequest(system=system, messages=messages, tools=tools), on_usage
        )

    async def vision(
        self,
        prompt: str,
        images: list[ImagePart],
        *,
        role: str = "vision",
        system: str | None = None,
        on_usage: UsageSink = _discard,
    ) -> Completion:
        return await self.complete(
            role,
            LLMRequest(system=system, messages=[Message.user(prompt, images)]),
            on_usage,
        )


def build_gateway(settings: Settings, extra_adapters: dict[str, Any] | None = None) -> Gateway:
    """Wire adapters for every provider the active profile uses, from env keys."""
    routing = RoutingTable.load(settings.llm_routing_profile)
    adapters: dict[str, ProviderAdapter] = {}
    for provider in routing.providers():
        if provider == "anthropic" and settings.anthropic_api_key:
            from kehora_llm.adapters.anthropic_adapter import AnthropicAdapter

            adapters[provider] = AnthropicAdapter(settings.anthropic_api_key.get_secret_value())
        elif provider == "openai" and settings.openai_api_key:
            from kehora_llm.adapters.openai_adapter import OpenAIAdapter

            adapters[provider] = OpenAIAdapter(settings.openai_api_key.get_secret_value())
        elif provider == "gemini" and settings.gemini_api_key:
            from kehora_llm.adapters.gemini_adapter import GeminiAdapter

            adapters[provider] = GeminiAdapter(settings.gemini_api_key.get_secret_value())
        elif provider == "fake":
            from kehora_llm.adapters.fake import FakeAdapter

            adapters[provider] = FakeAdapter()
    adapters.update(extra_adapters or {})
    if not adapters:
        raise FatalLLMError(
            f"profile {settings.llm_routing_profile!r} has no usable provider; set "
            "GEMINI_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY, or LLM_ROUTING_PROFILE=test"
        )
    return Gateway(routing, adapters)
