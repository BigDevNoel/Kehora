# Kehora
Kehora is an AI Company

Kehora is an AI hardware studio: describe a physical thing in plain language and get it
designed, verified and ready to make. That covers 3D-printed objects, electronics with
firmware, the enclosure that fits them, laser-cut parts and the app that controls the device.

The product spec is in [`docs/PRD.md`](docs/PRD.md), and the engineering rules are in
[`CLAUDE.md`](CLAUDE.md). Decisions are recorded in [`docs/decisions/`](docs/decisions/), and
the current status is in [`docs/HANDOFF.md`](docs/HANDOFF.md).

## Layout

- `Frontend/`: pnpm workspace with the studio (React + Vite), the public site (Astro) and the
  admin console.
- `Backend/`: uv workspace with the API (FastAPI), agents (LangGraph), engines (CAD,
  printability and more), the model gateway, schemas, database and evals.

## Run it locally

You need Docker, `uv` and `pnpm`.

```
cp .env.example .env    # fill in the Clerk keys and GEMINI_API_KEY
make dev                # studio :5173, admin :5174, site :4321, api :8000/docs
make check              # lint, types, tests and the end-to-end suite
```
