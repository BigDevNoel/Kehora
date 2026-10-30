import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from pydantic import ValidationError as PydanticValidationError
from referencing import Registry, Resource

from kehora_schemas import BuildState, ProjectSpec, RunEvent, RunEventType

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"


def _registry() -> Registry[Any]:
    resources = []
    for path in SCHEMA_DIR.glob("*.schema.json"):
        doc = json.loads(path.read_text())
        resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / name).read_text())
    return Draft202012Validator(schema, registry=_registry())


VALID_SPEC = {
    "schema_version": 0,
    "kind": "object",
    "title": "Phone stand",
    "summary": "A desk stand for a 6.5 inch phone at 60 degrees.",
    "requirements": ["Holds phone in portrait and landscape"],
    "dimensions": {"width_mm": 80, "depth_mm": 90, "height_mm": 110},
    "constraints": {"budget": {"amount_minor": 500000, "currency": "NGN"}, "material": "PLA"},
    "success_criteria": ["Prints without supports"],
}


@pytest.mark.parametrize("path", sorted(SCHEMA_DIR.glob("*.schema.json")), ids=lambda p: p.name)
def test_schemas_are_valid_draft_2020_12(path: Path) -> None:
    Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_project_spec_accepts_valid_and_matches_pydantic() -> None:
    _validator("project_spec.schema.json").validate(VALID_SPEC)
    spec = ProjectSpec.model_validate(VALID_SPEC)
    assert spec.constraints is not None and spec.constraints.budget is not None
    assert spec.constraints.budget.amount_minor == 500000


@pytest.mark.parametrize(
    "patch",
    [
        {"kind": "weapon"},
        {"constraints": {"budget": {"amount_minor": 10.5, "currency": "NGN"}}},
        {"constraints": {"budget": {"amount_minor": 100, "currency": "naira"}}},
        {"surprise": True},
    ],
)
def test_project_spec_rejects_invalid_in_both_languages(patch: dict[str, Any]) -> None:
    bad = {**VALID_SPEC, **patch}
    with pytest.raises(ValidationError):
        _validator("project_spec.schema.json").validate(bad)
    with pytest.raises(PydanticValidationError):
        ProjectSpec.model_validate(bad)


def test_run_event_types_match_prd() -> None:
    assert {t.value for t in RunEventType} == {
        "run_started",
        "node_started",
        "node_finished",
        "artifact_created",
        "check_passed",
        "check_warned",
        "check_failed",
        "repair_attempt",
        "needs_input",
        "needs_approval",
        "cost_update",
        "run_finished",
        "run_failed",
    }


def test_run_event_and_build_state_round_trip() -> None:
    event = {
        "run_id": "0192f0e2-7c4a-7000-8000-000000000001",
        "seq": 1,
        "type": "run_started",
        "payload": {},
        "created_at": "2026-10-30T12:00:00Z",
    }
    _validator("run_event.schema.json").validate(event)
    assert RunEvent.model_validate(event).seq == 1

    state = {
        "run_id": event["run_id"],
        "project_id": event["run_id"],
        "org_id": event["run_id"],
        "prompt": "a phone stand",
        "spec": VALID_SPEC,
    }
    _validator("build_state.schema.json").validate(state)
    parsed = BuildState.model_validate(state)
    assert parsed.spec is not None and parsed.artifacts == []
