"""2D/flat-pack spec + thickness -> SVG, DXF, nesting.

Interface stub; implemented in phase 3.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class LaserInput(BaseModel):
    pass


class LaserOutput(BaseModel):
    pass


class LaserEngine(NotYetImplementedEngine[LaserInput, LaserOutput]):
    name: ClassVar[str] = "laser"
    phase: ClassVar[int] = 3
