"""Board + pin map + behaviour -> PlatformIO project, binary.

Interface stub; implemented in phase 2.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class FirmwareInput(BaseModel):
    pass


class FirmwareOutput(BaseModel):
    pass


class FirmwareEngine(NotYetImplementedEngine[FirmwareInput, FirmwareOutput]):
    name: ClassVar[str] = "firmware"
    phase: ClassVar[int] = 2
