"""Builders turn an eval case into a build123d script.

- `reference`: hand-written scripts in `evals/objects/reference/`; proves the cases and the
  harness are achievable.
- `agent`: the real pipeline minus the database: spec writer, then the mechanical agent with its
  repair loop (ADR-0012). Needs model keys (or LLM_ROUTING_PROFILE=test for a dry run).
"""

from typing import Protocol

from pydantic import BaseModel

from evals.cases import EVALS_DIR, ObjectCase
from kehora_agents import prompts
from kehora_agents.mechanical import design_part
from kehora_common.settings import Settings
from kehora_engines_runner.runner import build_sandbox
from kehora_llm.errors import LLMError
from kehora_llm.gateway import Gateway, build_gateway
from kehora_llm.types import Message
from kehora_schemas import Constraints, ProjectSpec


class Built(BaseModel):
    script: str | None = None
    error: str | None = None
    repair_attempts: int = 0


class Builder(Protocol):
    name: str

    async def build(self, case: ObjectCase) -> Built | None:
        """None means this builder has nothing for the case (it is skipped, not failed)."""
        ...


class ReferenceBuilder:
    name = "reference"

    def __init__(self, suite: str = "objects") -> None:
        self.dir = EVALS_DIR / suite / "reference"

    async def build(self, case: ObjectCase) -> Built | None:
        path = self.dir / f"{case.id}.py"
        return Built(script=path.read_text(encoding="utf-8")) if path.exists() else None


class AgentBuilder:
    name = "agent"

    def __init__(self, suite: str = "objects", gateway: Gateway | None = None) -> None:
        settings = Settings()
        self.gateway = gateway or build_gateway(settings)
        self.sandbox = build_sandbox(settings)

    async def build(self, case: ObjectCase) -> Built | None:
        try:
            spec = await self.gateway.structured(
                "spec",
                ProjectSpec,
                [Message.user(f"Category from intake: object\n\nRequest:\n{case.prompt}")],
                system=prompts.load(*prompts.SPEC),
            )
        except LLMError as e:
            return Built(error=f"spec: {e}")
        # The case fixes the printer and material; the spec writer cannot know them.
        constraints = (spec.constraints or Constraints()).model_copy(
            update={"printer": case.printer, "material": case.material}
        )
        spec = spec.model_copy(update={"constraints": constraints})
        try:
            result = await design_part(self.gateway, self.sandbox, spec)
        except LLMError as e:
            return Built(error=f"mechanical: {e}")
        return Built(script=result.final.design.script, repair_attempts=result.repair_attempts)


BUILDERS: dict[str, type[ReferenceBuilder] | type[AgentBuilder]] = {
    "reference": ReferenceBuilder,
    "agent": AgentBuilder,
}
