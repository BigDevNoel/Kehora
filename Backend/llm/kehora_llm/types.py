"""Provider-neutral request/response types. Agents only ever see these, never SDK types."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImagePart(BaseModel):
    type: Literal["image"] = "image"
    media_type: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    data_b64: str


Part = TextPart | ImagePart


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: list[Part]

    @classmethod
    def user(cls, text: str, images: list[ImagePart] | None = None) -> "Message":
        return cls(role="user", content=[*(images or []), TextPart(text=text)])


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    input: dict[str, Any]


Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMRequest(BaseModel):
    system: str | None = None
    messages: list[Message]
    max_tokens: int = 16000
    tools: list[ToolSpec] = Field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    effort: Effort | None = None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Completion(BaseModel):
    provider: str
    model: str
    text: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: str | None = None
    usage: Usage = Field(default_factory=Usage)


class TextDelta(BaseModel):
    type: Literal["text_delta"] = "text_delta"
    text: str


class StreamDone(BaseModel):
    type: Literal["done"] = "done"
    completion: Completion


StreamEvent = TextDelta | StreamDone


class UsageRecord(BaseModel):
    """One model call, as logged per run (feeds credits and billing)."""

    role: str
    provider: str
    model: str
    usage: Usage
    cost_usd_micros: int | None
    latency_ms: int
    fallback_from: str | None = None
