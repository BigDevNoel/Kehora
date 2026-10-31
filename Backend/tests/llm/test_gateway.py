from decimal import Decimal

import pytest
from pydantic import BaseModel

from kehora_common.settings import Settings
from kehora_llm.adapters.fake import FakeAdapter, minimal_instance
from kehora_llm.errors import FatalLLMError, OutputValidationError, RetryableLLMError
from kehora_llm.gateway import Gateway, build_gateway
from kehora_llm.routing import ModelRef, Price, PriceBook, RoutingTable
from kehora_llm.types import (
    Completion,
    ImagePart,
    LLMRequest,
    Message,
    StreamDone,
    TextDelta,
    ToolSpec,
    Usage,
    UsageRecord,
)
from kehora_schemas import ProjectSpec


def _gateway(primary: FakeAdapter, backup: FakeAdapter) -> Gateway:
    routing = RoutingTable(
        {"spec": [ModelRef("p1", "big"), ModelRef("p2", "backup")], "solo": [ModelRef("p1", "big")]}
    )
    prices = PriceBook({"p1/big": Price(*(Decimal(x) for x in ("4", "20", "0.2", "5")))})
    return Gateway(routing, {"p1": primary, "p2": backup}, prices)


def _fakes() -> tuple[FakeAdapter, FakeAdapter]:
    a, b = FakeAdapter(), FakeAdapter()
    a.provider, b.provider = "p1", "p2"
    return a, b


REQ = LLMRequest(messages=[Message.user("a phone stand")])


def test_routing_profiles_load_and_reject_unknown() -> None:
    table = RoutingTable.load("default")
    assert str(table.chain("spec")[0]) == "gemini/gemini-3.8-flash"  # temporary, ADR-0013
    assert str(table.chain("repair")[0]) == "gemini/gemini-3.8-flash"
    assert table.providers() == {"gemini", "anthropic", "openai"}
    assert RoutingTable.load("test").providers() == {"fake"}
    with pytest.raises(ValueError, match="unknown LLM routing profile"):
        RoutingTable.load("nope")
    with pytest.raises(ValueError):
        ModelRef.parse("no-slash")


def test_cost_is_exact_usd_micros_rounded_up() -> None:
    book = PriceBook.load()
    opus = ModelRef("anthropic", "claude-opus-5-5")
    assert (
        book.cost_usd_micros(opus, Usage(input_tokens=1_000_000, output_tokens=1_000_000))
        == 24_000_000
    )
    haiku = ModelRef("anthropic", "claude-haiku-5-5")
    assert book.cost_usd_micros(haiku, Usage(input_tokens=3)) == 1  # 0.3 micros rounds up
    assert book.cost_usd_micros(ModelRef("openai", "gpt-unknown"), Usage(input_tokens=1)) is None


async def test_complete_records_usage_and_cost() -> None:
    primary, backup = _fakes()
    primary.scripted.append(
        Completion(
            provider="p1", model="big", text="hi", usage=Usage(input_tokens=10, output_tokens=5)
        )
    )
    records: list[UsageRecord] = []

    async def sink(r: UsageRecord) -> None:
        records.append(r)

    out = await _gateway(primary, backup).complete("spec", REQ, sink)
    assert out.text == "hi"
    assert records[0].cost_usd_micros == 10 * 4 + 5 * 20
    assert records[0].fallback_from is None


async def test_retryable_error_falls_back_to_next_model() -> None:
    primary, backup = _fakes()
    primary.scripted.append(RetryableLLMError("529 overloaded"))
    records: list[UsageRecord] = []

    async def sink(r: UsageRecord) -> None:
        records.append(r)

    out = await _gateway(primary, backup).complete("spec", REQ, sink)
    assert out.provider == "p2"
    assert records[0].fallback_from == "p1/big"
    assert records[0].cost_usd_micros is None  # backup has no price configured


async def test_fatal_error_does_not_fall_back() -> None:
    primary, backup = _fakes()
    primary.scripted.append(FatalLLMError("400 bad request"))
    with pytest.raises(FatalLLMError):
        await _gateway(primary, backup).complete("spec", REQ)
    assert backup.calls == []


async def test_exhausted_chain_raises_last_error() -> None:
    primary, _ = _fakes()
    primary.scripted.append(RetryableLLMError("timeout"))
    with pytest.raises(RetryableLLMError):
        await _gateway(primary, FakeAdapter()).complete("solo", REQ)


async def test_stream_yields_deltas_then_done_and_falls_back_before_first_token() -> None:
    primary, backup = _fakes()
    primary.scripted.append(RetryableLLMError("timeout"))
    events = [e async for e in _gateway(primary, backup).stream("spec", REQ)]
    assert isinstance(events[-1], StreamDone)
    assert events[-1].completion.provider == "p2"
    assert (
        "".join(e.text for e in events if isinstance(e, TextDelta))
        .strip()
        .endswith("a phone stand")
    )


async def test_structured_returns_validated_project_spec() -> None:
    gw = build_gateway(Settings(llm_routing_profile="test", _env_file=None))
    spec = await gw.structured("spec", ProjectSpec, [Message.user("Phone stand for my desk")])
    assert isinstance(spec, ProjectSpec)
    assert spec.schema_version == 0 and spec.kind.value == "object"
    assert spec.title == "Phone stand for my desk"


async def test_structured_rejects_invalid_output() -> None:
    primary, backup = _fakes()
    primary.scripted.append(Completion(provider="p1", model="big", text='{"title": 1}'))

    class Out(BaseModel):
        title: str

    with pytest.raises(OutputValidationError):
        await _gateway(primary, backup).structured("spec", Out, [Message.user("x")])


async def test_tool_call_and_vision_pass_tools_and_images() -> None:
    primary, backup = _fakes()
    gw = _gateway(primary, backup)
    tool = ToolSpec(name="run_cad", description="Run a CAD script", input_schema={"type": "object"})
    await gw.tool_call("spec", [Message.user("make it")], [tool])
    assert primary.calls[-1][1].tools == [tool]

    img = ImagePart(media_type="image/png", data_b64="iVBORw0KGgo=")
    await gw.vision("what part is this?", [img], role="spec")
    assert primary.calls[-1][1].messages[0].content[0] == img


def test_build_gateway_requires_a_usable_provider() -> None:
    with pytest.raises(FatalLLMError, match="no usable provider"):
        build_gateway(Settings(llm_routing_profile="default", _env_file=None))


def test_gemini_key_alone_is_a_usable_gateway() -> None:
    gw = build_gateway(
        Settings(llm_routing_profile="default", gemini_api_key="g-test", _env_file=None)
    )
    assert set(gw.adapters) == {"gemini"}
    assert [str(ref) for ref, _ in gw._candidates("mechanical")] == ["gemini/gemini-3.8-flash"]


def test_minimal_instance_handles_refs_nullables_and_enums() -> None:
    schema = {
        "type": "object",
        "required": ["a", "b", "c", "d"],
        "properties": {
            "a": {"$ref": "#/$defs/K"},
            "b": {"anyOf": [{"type": "null"}, {"type": "integer", "minimum": 3}]},
            "c": {"type": ["string", "null"], "maxLength": 2},
            "d": {"type": "array"},
        },
        "$defs": {"K": {"enum": ["x", "y"]}},
    }
    assert minimal_instance(schema, "seed") == {"a": "x", "b": 3, "c": "se", "d": []}
