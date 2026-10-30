"""Shared data shapes. Source of truth is the JSON Schema next to this package;
everything under `generated/` is written by `make codegen` and must not be edited by hand."""

from kehora_schemas.generated.build_state_schema import (
    ArtifactRef,
    ArtifactType,
    BuildState,
    CheckResult,
    CheckStatus,
)
from kehora_schemas.generated.intake_result_schema import (
    IntakeResult,
    PolicyCategory,
    PolicyDecision,
)
from kehora_schemas.generated.project_spec_schema import (
    ComponentRequirement,
    Constraints,
    Dimensions,
    Money,
    ProjectKind,
    ProjectSpec,
)
from kehora_schemas.generated.run_event_schema import RunEvent, RunEventType

__all__ = [
    "ArtifactRef",
    "ArtifactType",
    "BuildState",
    "CheckResult",
    "CheckStatus",
    "ComponentRequirement",
    "Constraints",
    "Dimensions",
    "IntakeResult",
    "Money",
    "PolicyCategory",
    "PolicyDecision",
    "ProjectKind",
    "ProjectSpec",
    "RunEvent",
    "RunEventType",
]
