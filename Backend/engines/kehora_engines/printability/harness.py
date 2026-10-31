"""Runs inside the CAD sandbox image, never on the host (ADR-0011).

Loads /work/in/part.stl, runs `analysis.analyze` (shipped next to this file) with the printer and
material from /work/in/params.json, and writes /work/out/report.json. A mesh that will not load
exits 3 with the reason in load_error.txt.
"""

import json
from pathlib import Path

import trimesh
from analysis import analyze  # type: ignore[import-not-found]  # sibling file in /work/in

IN = Path("/work/in")
OUT = Path("/work/out")


def _load_error(message: str) -> int:
    (OUT / "load_error.txt").write_text(message)
    return 3


def main() -> int:
    params = json.loads((IN / "params.json").read_text())
    try:
        mesh = trimesh.load_mesh(str(IN / "part.stl"), file_type="stl")
    except Exception as e:
        return _load_error(f"{type(e).__name__}: {e}")
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        return _load_error("the file contains no triangles")
    report = analyze(mesh, params["printer"], params["material"], params["samples"], params["seed"])
    (OUT / "report.json").write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
