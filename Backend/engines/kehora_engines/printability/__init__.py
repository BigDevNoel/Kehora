"""Mesh + printer profile + material -> walls, overhangs, bed fit report.

Interface stub; implemented in phase 1.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class PrintabilityInput(BaseModel):
    pass


class PrintabilityOutput(BaseModel):
    pass


class PrintabilityEngine(NotYetImplementedEngine[PrintabilityInput, PrintabilityOutput]):
    name: ClassVar[str] = "printability"
    phase: ClassVar[int] = 1
