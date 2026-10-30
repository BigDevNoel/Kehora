"""Device spec + firmware protocol -> PWA bundle.

Interface stub; implemented in phase 3.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class AppBuilderInput(BaseModel):
    pass


class AppBuilderOutput(BaseModel):
    pass


class AppBuilderEngine(NotYetImplementedEngine[AppBuilderInput, AppBuilderOutput]):
    name: ClassVar[str] = "app_builder"
    phase: ClassVar[int] = 3
