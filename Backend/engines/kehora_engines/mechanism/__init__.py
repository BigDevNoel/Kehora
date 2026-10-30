"""Motion spec -> assembly + collision-checked motion preview.

Interface stub; implemented in phase 3.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class MechanismInput(BaseModel):
    pass


class MechanismOutput(BaseModel):
    pass


class MechanismEngine(NotYetImplementedEngine[MechanismInput, MechanismOutput]):
    name: ClassVar[str] = "mechanism"
    phase: ClassVar[int] = 3
