# ADR-0012: Mechanical agent and repair loop

- Status: proposed
- Date: 2026-10-30

## Context

PRD 6: specialist subgraphs produce outputs, verifiers check them with real tools, failures go
back to the specialist up to 5 times, then escalate. PRD 8.2 gate: 90% of `evals/objects` pass.
Phase 1 starts with single-part functional objects.

## Decision

- **Loop** `kehora_agents/mechanical.py::design_part(gateway, sandbox, spec)`, free of the
  database and event stream so the graph and the eval runner share it:
  1. `mechanical` role (strongest tier) writes a `MechanicalDesign`: build123d script,
     `intended_size_mm`, notes (`Backend/schemas/mechanical_design.schema.json`).
  2. CAD engine runs it; its `dimensions` check compares the solid with `intended_size_mm`, which
     catches scripts that do not build what they meant. The spec's own dimensions are often
     approximate, so they guide the prompt but are not checked to 0.1 mm here; the evals check
     them per case.
  3. If CAD passes, the printability engine runs on the spec's printer and material (free-text
     match to shipped profiles; default Prusa MK4 + PLA). Errors fail; warnings pass through to
     the user.
  4. Failures go to the `repair` role (cheaper tier) with the brief, the previous script and the
     verifier messages. At most 5 repairs; each emits `repair_attempt`.
- **Prompts** `mechanical.v1.md`, `mechanical_repair.v1.md`: script contract, print rules
  scaled to the printer/material, a build123d cheat sheet. Spec text and verifier output are
  data, not instructions.
- **Graph:** after `create_version`, `object` projects go to the `mechanical` node when
  `FEATURE_PHASE1_OBJECTS` is on; everything else keeps the Phase 0 echo engine. The node stores
  `script.py`, `part.step`, `part.stl` and `part.3mf` (CAD checks on the STEP, printability on
  the STL) and fails the run with `VerificationFailed` if the last attempt still fails.
- **Evals:** `python -m evals --builder agent` runs spec writer + `design_part` per case; the
  runner then re-verifies the final script itself.

## Consequences

- A worker crash mid-loop restarts the node: LLM calls repeat (cost), outputs stay idempotent.
  Checkpointing each attempt is a later optimisation.
- One part per project. Assemblies and multi-part prints come with the planner.
- No escalation question to the user yet after 5 failures; the run fails with the reasons.
