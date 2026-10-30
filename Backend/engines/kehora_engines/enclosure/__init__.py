"""PCB 3D model + ports + style -> printable case.

Interface stub; implemented in phase 2.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class EnclosureInput(BaseModel):
    pass


class EnclosureOutput(BaseModel):
    pass


class EnclosureEngine(NotYetImplementedEngine[EnclosureInput, EnclosureOutput]):
    name: ClassVar[str] = "enclosure"
    phase: ClassVar[int] = 2
