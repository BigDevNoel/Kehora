from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import Any

import yaml

from kehora_llm.types import Usage

CONFIG_DIR = Path(__file__).parent / "config"


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

    @classmethod
    def parse(cls, ref: str) -> "ModelRef":
        provider, sep, model = ref.partition("/")
        if not sep or not provider or not model:
            raise ValueError(f"model ref must be '<provider>/<model>': {ref!r}")
        return cls(provider, model)

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"


class RoutingTable:
    def __init__(self, roles: dict[str, list[ModelRef]]) -> None:
        self._roles = roles

    @classmethod
    def load(cls, profile: str, path: Path = CONFIG_DIR / "routing.yaml") -> "RoutingTable":
        data: dict[str, Any] = yaml.safe_load(path.read_text())
        profiles = data["profiles"]
        if profile not in profiles:
            raise ValueError(f"unknown LLM routing profile {profile!r}; have {sorted(profiles)}")
        return cls(
            {role: [ModelRef.parse(r) for r in chain] for role, chain in profiles[profile].items()}
        )

    def chain(self, role: str) -> list[ModelRef]:
        try:
            return self._roles[role]
        except KeyError:
            raise ValueError(f"no route for role {role!r}") from None

    def providers(self) -> set[str]:
        return {ref.provider for chain in self._roles.values() for ref in chain}


@dataclass(frozen=True)
class Price:
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


class PriceBook:
    def __init__(self, prices: dict[str, Price]) -> None:
        self._prices = prices

    @classmethod
    def load(cls, path: Path = CONFIG_DIR / "pricing.yaml") -> "PriceBook":
        data: dict[str, Any] = yaml.safe_load(path.read_text())
        return cls(
            {
                ref: Price(**{k: Decimal(str(v)) for k, v in p.items()})
                for ref, p in data["models"].items()
            }
        )

    def cost_usd_micros(self, ref: ModelRef, usage: Usage) -> int | None:
        """tokens x (USD per 1M tokens) is exactly USD micros; round up to whole micros."""
        price = self._prices.get(str(ref))
        if price is None:
            return None
        total = (
            usage.input_tokens * price.input
            + usage.output_tokens * price.output
            + usage.cache_read_tokens * price.cache_read
            + usage.cache_write_tokens * price.cache_write
        )
        return int(total.to_integral_value(rounding=ROUND_CEILING))
