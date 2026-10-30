"""`make evals`: run every suite under Backend/evals and print pass rates.

Each suite is a folder of `*.yaml` cases. Phase 0 ships the runner with empty suites; Phase 1
adds `objects/` (gate: 90% pass). A suite with no cases reports 0/0 and does not fail.
"""

import sys
from pathlib import Path

SUITES = ("objects", "devices", "enclosures", "mechanisms")


def main() -> int:
    root = Path(__file__).parent
    for suite in SUITES:
        cases = sorted((root / suite).glob("*.yaml"))
        print(f"{suite:<12} {0}/{len(cases)} passed" if cases else f"{suite:<12} no cases yet")
        if cases:
            print("  case execution arrives with the phase 1 eval harness", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
