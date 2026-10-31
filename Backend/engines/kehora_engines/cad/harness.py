"""Runs inside the CAD sandbox image, never on the host (ADR-0010).

Executes /work/in/script.py (a build123d script that assigns `result`), exports STEP, STL and
3MF to /work/out, and writes /work/out/report.json with measurements and mesh checks.

Script failures are reported in report.json with exit code 0 so the repair loop gets a clean
error message; a non-zero exit means the harness itself broke.
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Any

IN = Path("/work/in")
OUT = Path("/work/out")
SCRIPT_NAME = "script.py"
MAX_ERROR_CHARS = 4000


def _report(data: dict[str, Any]) -> None:
    (OUT / "report.json").write_text(json.dumps(data, indent=2))


def _script_error(stage: str, message: str) -> None:
    _report({"ok": False, "stage": stage, "error": message[-MAX_ERROR_CHARS:]})


def _script_traceback() -> str:
    """Traceback limited to frames from the user's script, so the repair loop sees its own code."""
    exc_type, exc, tb = sys.exc_info()
    frames = [f for f in traceback.extract_tb(tb) if f.filename == SCRIPT_NAME]
    lines = traceback.format_list(frames) + traceback.format_exception_only(exc_type, exc)
    return "".join(lines)


def _resolve_shape(value: Any) -> Any:
    from build123d import Shape

    # A BuildPart/BuildSketch context: take the object it built.
    if not isinstance(value, Shape) and hasattr(value, "part"):
        value = value.part
    return value if isinstance(value, Shape) else None


def main() -> int:
    params = json.loads((IN / "params.json").read_text())
    source = (IN / SCRIPT_NAME).read_text()

    namespace: dict[str, Any] = {"__name__": "__main__"}
    try:
        exec(compile(source, SCRIPT_NAME, "exec"), namespace)  # noqa: S102 - sandboxed by design
    except BaseException:
        _script_error("script", _script_traceback())
        return 0

    if "result" not in namespace:
        _script_error(
            "result", "the script must assign the final part to a variable named `result`"
        )
        return 0
    shape = _resolve_shape(namespace["result"])
    if shape is None:
        kind = type(namespace["result"]).__name__
        _script_error("result", f"`result` must be a build123d Shape or BuildPart, got {kind}")
        return 0
    if not shape.solids():
        # Faces or wires only: printers and the 3MF exporter need a closed solid.
        found = f"{len(shape.faces())} faces, {len(shape.edges())} edges"
        _script_error("result", f"`result` contains no solid ({found}); extrude or close it")
        return 0

    from build123d import Mesher, export_step, export_stl

    try:
        export_step(shape, str(OUT / "part.step"))
        export_stl(
            shape,
            str(OUT / "part.stl"),
            tolerance=params["linear_tolerance_mm"],
            angular_tolerance=params["angular_tolerance_rad"],
        )
        mesher = Mesher()
        mesher.add_shape(
            shape,
            linear_deflection=params["linear_tolerance_mm"],
            angular_deflection=params["angular_tolerance_rad"],
        )
        mesher.write(str(OUT / "part.3mf"))
    except Exception:
        _script_error("export", traceback.format_exc())
        return 0

    import trimesh

    mesh = trimesh.load_mesh(str(OUT / "part.stl"))
    bbox = shape.bounding_box()
    _report(
        {
            "ok": True,
            "brep": {
                "is_valid": bool(shape.is_valid),
                "solid_count": len(shape.solids()),
                "volume_mm3": float(shape.volume),
                "area_mm2": float(shape.area),
                "bbox_min_mm": [bbox.min.X, bbox.min.Y, bbox.min.Z],
                "bbox_max_mm": [bbox.max.X, bbox.max.Y, bbox.max.Z],
            },
            "mesh": {
                "triangles": len(mesh.faces),
                "is_watertight": bool(mesh.is_watertight),
                "is_winding_consistent": bool(mesh.is_winding_consistent),
                "volume_mm3": float(mesh.volume),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
