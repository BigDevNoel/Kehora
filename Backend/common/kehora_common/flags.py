"""Feature flags (CLAUDE.md rule 10).

Flags are declared here with their default and overridden per environment with
`FEATURE_<NAME>=true|false`. Phase-gated work ships dark behind a flag.
"""

import os
from enum import StrEnum


class Flag(StrEnum):
    CREDITS_ENFORCED = "credits_enforced"


_DEFAULTS: dict[Flag, bool] = {
    Flag.CREDITS_ENFORCED: False,
}


def is_enabled(flag: Flag) -> bool:
    raw = os.environ.get(f"FEATURE_{flag.value.upper()}")
    if raw is None:
        return _DEFAULTS[flag]
    return raw.strip().lower() in {"1", "true", "yes", "on"}
