from collections.abc import AsyncIterator
from typing import Protocol

from kehora_llm.types import Completion, LLMRequest, StreamEvent


class ProviderAdapter(Protocol):
    """One per provider. The only place a provider SDK may be imported (CLAUDE.md rule 3)."""

    provider: str

    async def complete(self, model: str, request: LLMRequest) -> Completion: ...

    def stream(self, model: str, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        """Yield TextDelta events, then exactly one StreamDone."""
        ...
