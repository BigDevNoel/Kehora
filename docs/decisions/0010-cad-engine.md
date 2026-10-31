# ADR-0010: CAD engine sandbox image and script contract

- Status: proposed
- Date: 2026-10-30

## Context

PRD 7: the mechanical engine runs a build123d script and returns STEP, STL, 3MF, renders and
dimensions; its verifier checks the script runs, the solid is valid and watertight, and the
dimensions are within ±0.1 mm of the spec. Rule 4: generated scripts only run in sandboxes.
Phase 1 started before the Phase 0 Playwright gate ran (blocked on Clerk keys); the owner
approved working ahead on backend engines.

## Decision

- **Image** `kehora/engine-cad:0.13.0` (`Backend/infra/docker/engines/cad`): Python 3.12,
  build123d 0.13.0 (OCP 8.0, no VTK) and trimesh 5.1.1, installed from a hashed lock file.
  Built locally by `make engine-images` (a dependency of `make services`, so CI builds it).
  The tag is the build123d version; a test checks the Makefile and the engine agree.
- **Script contract:** a script assigns its final part to `result` (a `Shape` or a
  `BuildPart`). Units are millimetres.
- **Harness** (`kehora_engines/cad/harness.py`) is shipped into each job as an input file, so
  the image holds only libraries. It always writes `report.json`; script errors, a missing
  `result` and export failures exit 0 with `ok: false`, a `stage` and a traceback trimmed to the
  script's own frames, so the repair loop gets a clean message. A non-zero exit means the
  harness broke (`EngineError`).
- **Checks:** `script_runs`, `solid_valid` (OCCT valid, >= 1 solid, volume > 0), `watertight`
  (trimesh on the exported STL: watertight and consistent winding), `dimensions` (bounding box
  per axis against `expected_size_mm` when the spec gives it), and a `single_body` warning when
  there is more than one solid.
- Limits: 2 CPUs, 2 GB, 5-minute timeout, no network.

## Consequences

- Renders (PNG) are not produced here; they come from a render engine later in phase 1.
- Dimension checks cover the overall bounding box only. Feature-level dimensions (hole
  diameters, wall thickness) need named measurements in the spec; revisit with the printability
  engine.
- The image is about 1 GB; first `make services` is slow.
