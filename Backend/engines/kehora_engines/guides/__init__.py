"""Project bundle -> assembly guide steps, renders, PDF.

Interface stub; implemented in phase 3.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class GuidesInput(BaseModel):
    pass


class GuidesOutput(BaseModel):
    pass


class GuidesEngine(NotYetImplementedEngine[GuidesInput, GuidesOutput]):
    name: ClassVar[str] = "guides"
    phase: ClassVar[int] = 3
