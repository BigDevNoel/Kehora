"""Deterministic offline adapter for tests and `make check` (LLM_ROUTING_PROFILE=test).

Structured requests get the minimal instance that satisfies the requested JSON Schema, with
strings derived from the last user message, so pipelines run end to end without a network.
Scripted responses can be queued for unit tests.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from kehora_llm.types import Completion, LLMRequest, StreamDone, StreamEvent, TextDelta, Usage


def _last_user_text(request: LLMRequest) -> str:
    for m in reversed(request.messages):
        if m.role == "user":
            for p in reversed(m.content):
                if p.type == "text":
                    return p.text
    return "request"


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        node: Any = root
        for key in ref[2:].split("/"):
            node = node[key]
        return _resolve(node, root)
    return schema


def minimal_instance(schema: dict[str, Any], seed: str, root: dict[str, Any] | None = None) -> Any:
    root = root or schema
    schema = _resolve(schema, root)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [_resolve(o, root) for o in schema[key]]
            non_null = [o for o in options if o.get("type") != "null"]
            return minimal_instance((non_null or options)[0], seed, root)
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    match kind:
        case "object":
            props = schema.get("properties", {})
            return {
                name: minimal_instance(props[name], seed, root)
                for name in schema.get("required", [])
            }
        case "array":
            return []
        case "string":
            limit = schema.get("maxLength", 200)
            return (seed or "x")[:limit]
        case "integer":
            return int(schema.get("minimum", 0))
        case "number":
            return float(schema.get("minimum", 0))
        case "boolean":
            return False
        case "null":
            return None
    return None


class FakeAdapter:
    provider = "fake"

    def __init__(self) -> None:
        self.scripted: list[Completion | Exception] = []
        self.calls: list[tuple[str, LLMRequest]] = []

    def _answer(self, model: str, request: LLMRequest) -> Completion:
        self.calls.append((model, request))
        if self.scripted:
            nxt = self.scripted.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        seed = _last_user_text(request)
        if request.output_schema is not None:
            text = json.dumps(minimal_instance(request.output_schema, seed))
        else:
            text = f"[fake:{model}] {seed}"
        return Completion(
            provider=self.provider,
            model=model,
            text=text,
            stop_reason="end_turn",
            usage=Usage(input_tokens=len(seed.split()) + 10, output_tokens=len(text.split())),
        )

    async def complete(self, model: str, request: LLMRequest) -> Completion:
        return self._answer(model, request)

    async def stream(self, model: str, request: LLMRequest) -> AsyncIterator[StreamEvent]:
        completion = self._answer(model, request)
        for word in completion.text.split(" "):
            yield TextDelta(text=word + " ")
        yield StreamDone(completion=completion)
