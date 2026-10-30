"""Netlist + board outline -> KiCad project, Gerbers, DRC.

Interface stub; implemented in phase 2.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class PcbInput(BaseModel):
    pass


class PcbOutput(BaseModel):
    pass


class PcbEngine(NotYetImplementedEngine[PcbInput, PcbOutput]):
    name: ClassVar[str] = "pcb"
    phase: ClassVar[int] = 2
