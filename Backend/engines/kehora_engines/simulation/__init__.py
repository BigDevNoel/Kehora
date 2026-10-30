"""Firmware + circuit -> Wokwi/ngspice test log.

Interface stub; implemented in phase 2.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class SimulationInput(BaseModel):
    pass


class SimulationOutput(BaseModel):
    pass


class SimulationEngine(NotYetImplementedEngine[SimulationInput, SimulationOutput]):
    name: ClassVar[str] = "simulation"
    phase: ClassVar[int] = 2
