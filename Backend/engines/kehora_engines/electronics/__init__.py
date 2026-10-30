"""Components + SKiDL script -> netlist, schematic, BOM, ERC.

Interface stub; implemented in phase 2.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class ElectronicsInput(BaseModel):
    pass


class ElectronicsOutput(BaseModel):
    pass


class ElectronicsEngine(NotYetImplementedEngine[ElectronicsInput, ElectronicsOutput]):
    name: ClassVar[str] = "electronics"
    phase: ClassVar[int] = 2
