"""Versioned prompt files (CLAUDE.md: never inline prompts). `load("spec", 1)` reads
`Backend/agents/prompts/spec.v1.md`. Bumping a prompt means adding a new file and changing the
version here, so evals can compare versions."""

from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

INTAKE = ("intake", 1)
SPEC = ("spec", 1)


@cache
def load(name: str, version: int) -> str:
    return (PROMPTS_DIR / f"{name}.v{version}.md").read_text(encoding="utf-8").strip()
