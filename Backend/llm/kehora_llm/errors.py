class LLMError(Exception):
    """Base class for gateway errors. Adapters translate SDK exceptions into these."""


class RetryableLLMError(LLMError):
    """Timeouts, 429, 5xx, connection errors: the gateway falls back to the next model."""


class FatalLLMError(LLMError):
    """Bad request, auth, not found: a bug or config error. No fallback; fail loudly."""


class RefusalError(LLMError):
    """The model (and any server-side fallback) declined the request on policy grounds."""

    def __init__(self, message: str, category: str | None = None) -> None:
        super().__init__(message)
        self.category = category


class OutputValidationError(LLMError):
    """Structured output did not validate against the requested schema."""
