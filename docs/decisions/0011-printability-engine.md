# ADR-0011: Printability engine

- Status: proposed
- Date: 2026-10-30

## Context

PRD 7: mesh + printer profile + material -> report on walls, overhangs, bridges, supports, bed
fit and orientation; no blocking errors may pass, warnings are shown. PRD 8.2: the report comes
with one-click fixes (reorient, thicken walls, add supports, split for bed size). The report and
profiles are shown in the studio, so they are shared shapes (rule 1).

## Decision

- **Schema** `Backend/schemas/printability.schema.json`: `PrintabilityReport`, `PrinterProfile`,
  `Material`, `PrintIssue` (code, severity, plain message, `fixes`).
- **Profiles** are YAML in `Backend/data/printer-profiles` and `Backend/data/materials`, validated
  against the schema on load. Shipped: Prusa MK4 and MINI+, Bambu X1C and A1 mini, Ender-3 V3,
  Neptune 4; PLA, PETG, ABS, TPU. FDM only for now.
- **Runs in the CAD sandbox image** (it already has trimesh and numpy), so there is no second
  image. `analysis.py` (pure numpy + trimesh, plain dicts) and `harness.py` are shipped into each
  job. The same numpy and trimesh versions are dev dependencies, so the analysis is unit-tested
  on the host and a docker test checks the sandbox gives the identical report.
- **Method:**
  - Orientation: six resting faces; each measured for bed fit (also turned 90 degrees on the
    bed), overhang area and bed contact. Recommended = fits, then least overhang, then lowest.
  - Overhang: downward faces steeper than the material's `max_overhang_deg` from vertical,
    excluding faces resting on the bed.
  - Walls: area-weighted surface samples cast a ray inward to the far wall (vectorised
    Möller-Trumbore, fixed seed, no rtree). Reported as the 2nd percentile. Under the nozzle on
    more than 1% of the surface is an error; under `min_wall_lines x nozzle` is a warning.
  - Errors: not watertight, exceeds bed, walls too thin. Warnings: thin walls, overhangs,
    small bed contact.
- **Verifier:** one `printable` check (fail if blocking, warn if any warning, else pass) whose
  report is the full `PrintabilityReport`; `mesh_loads` fails when the STL cannot be read.

## Consequences

- Bridges and support volume are left to the slicing engine, which sees real toolpaths.
- Wall rays are O(rays x triangles); 800 rays on a 100k-triangle mesh takes seconds. Add a BVH
  if large organic meshes get slow.
- Resin printers need different checks (islands, suction cups, drain holes): a later ADR.
