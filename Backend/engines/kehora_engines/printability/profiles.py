"""Shipped printer and material profiles from Backend/data (PRD 7)."""

from functools import cache
from pathlib import Path

import yaml

from kehora_schemas import Material, PrinterProfile

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@cache
def printers() -> dict[str, PrinterProfile]:
    return {
        p.id: p
        for p in (
            PrinterProfile.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
            for f in sorted((DATA_DIR / "printer-profiles").glob("*.yaml"))
        )
    }


@cache
def materials() -> dict[str, Material]:
    return {
        m.id: m
        for m in (
            Material.model_validate(yaml.safe_load(f.read_text(encoding="utf-8")))
            for f in sorted((DATA_DIR / "materials").glob("*.yaml"))
        )
    }
