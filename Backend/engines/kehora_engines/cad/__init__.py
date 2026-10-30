"""Mechanical code-CAD: build123d script -> STEP, STL, 3MF, renders, dimensions.

Interface stub; implemented in phase 1.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class CadInput(BaseModel):
    pass


class CadOutput(BaseModel):
    pass


class CadEngine(NotYetImplementedEngine[CadInput, CadOutput]):
    name: ClassVar[str] = "cad"
    phase: ClassVar[int] = 1
