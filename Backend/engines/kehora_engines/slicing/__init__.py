"""Mesh + profile -> G-code, print time, grams, cost.

Interface stub; implemented in phase 1.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class SlicingInput(BaseModel):
    pass


class SlicingOutput(BaseModel):
    pass


class SlicingEngine(NotYetImplementedEngine[SlicingInput, SlicingOutput]):
    name: ClassVar[str] = "slicing"
    phase: ClassVar[int] = 1
