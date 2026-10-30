"""Organic 3D and mesh repair: prompt/image mesh -> manifold GLB/STL.

Interface stub; implemented in phase 1.
"""

from typing import ClassVar

from pydantic import BaseModel

from kehora_engines.base import NotYetImplementedEngine


class MeshInput(BaseModel):
    pass


class MeshOutput(BaseModel):
    pass


class MeshEngine(NotYetImplementedEngine[MeshInput, MeshOutput]):
    name: ClassVar[str] = "mesh"
    phase: ClassVar[int] = 1
