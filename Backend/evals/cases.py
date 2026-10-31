"""Eval case format for the objects suite (PRD 8.2 gate: 90% of 100 prompts pass).

One YAML file per case in `evals/objects/`. A case passes when the final model is a valid,
watertight solid that prints on the target printer and material without blocking issues, and
meets the case's own expectations.
"""

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

EVALS_DIR = Path(__file__).resolve().parent


class Category(StrEnum):
    functional = "functional"  # code-CAD: brackets, boxes, hooks, stands
    organic = "organic"  # artistic shapes: vases, figurines
    hybrid = "hybrid"  # organic shape with functional features


class Range(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float | None = Field(default=None, gt=0)
    max: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> "Range":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must not exceed max")
        return self

    def contains(self, value: float) -> bool:
        return (self.min is None or value >= self.min) and (self.max is None or value <= self.max)


class ExactSize(BaseModel):
    """Sizes the prompt states outright. Compared orientation-free, largest to smallest."""

    model_config = ConfigDict(extra="forbid")

    dims_mm: list[float] = Field(min_length=1, max_length=3)
    tolerance_mm: float = Field(default=0.1, gt=0)


class Expect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Overall size, orientation-free: largest, middle and smallest bounding-box side.
    largest_mm: Range | None = None
    middle_mm: Range | None = None
    smallest_mm: Range | None = None
    exact_size: ExactSize | None = None
    single_body: bool = True
    supports_allowed: bool = True


class ObjectCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    prompt: str = Field(min_length=10)
    category: Category = Category.functional
    printer: str = "prusa-mk4"
    material: str = "pla"
    expect: Expect = Field(default_factory=Expect)
    notes: str | None = None


def load_cases(suite: str = "objects") -> list[ObjectCase]:
    cases = []
    for path in sorted((EVALS_DIR / suite).glob("*.yaml")):
        case = ObjectCase.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if case.id != path.stem:
            raise ValueError(f"{path.name}: id {case.id!r} must match the file name")
        cases.append(case)
    return cases
