"""Printability analysis (ADR-0011). Runs inside the CAD sandbox image via `harness.py`.

Pure numpy + trimesh with plain-dict inputs and outputs, so it needs nothing beyond the image
and the host tests can call it directly. The engine validates the result against the
`PrintabilityReport` schema.
"""

import math
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

BED_EPS_MM = 0.01  # a face this close to z = 0 rests on the bed
RAY_EPS_MM = 1e-4
RAY_CHUNK_ELEMENTS = 1_000_000  # rays x triangles per vectorised batch (memory bound)
THIN_FRACTION_LIMIT = 0.01  # flag walls when more than 1% of the surface is too thin
OVERHANG_MIN_AREA_MM2 = 25.0
SMALL_CONTACT_MM2 = 50.0

# Resting faces to try: as given, upside down, and each side down.
ORIENTATIONS: tuple[tuple[float, float, float], ...] = (
    (0, 0, 0),
    (180, 0, 0),
    (90, 0, 0),
    (-90, 0, 0),
    (0, 90, 0),
    (0, -90, 0),
)

Floats = NDArray[np.float64]


def analyze(
    mesh: trimesh.Trimesh,
    printer: dict[str, Any],
    material: dict[str, Any],
    samples: int = 800,
    seed: int = 0,
) -> dict[str, Any]:
    watertight = bool(mesh.is_watertight)
    results = [_orient(mesh, rot, printer, material) for rot in ORIENTATIONS]
    as_given = results[0]
    # Fit first, then least support, then lowest height. Ties keep the earlier (as given).
    recommended = min(
        results,
        key=lambda r: (not r["fits_bed"], round(r["overhang_area_mm2"], 1), r["size_mm"]["z"]),
    )

    nozzle = float(printer["nozzle_mm"])
    min_wall = nozzle * int(material["min_wall_lines"])
    thickness = _wall_thickness(mesh, samples, seed) if watertight else np.empty(0)
    finite = thickness[np.isfinite(thickness)]
    min_wall_mm = float(np.percentile(finite, 2)) if finite.size else None
    thin_fraction = float(np.mean(finite < min_wall)) if finite.size else 0.0
    too_thin_fraction = float(np.mean(finite < nozzle)) if finite.size else 0.0

    issues = _issues(
        watertight,
        as_given,
        recommended,
        min_wall,
        nozzle,
        thin_fraction,
        too_thin_fraction,
        min_wall_mm,
        float(mesh.area),
    )
    return {
        "printer_id": printer["id"],
        "material_id": material["id"],
        "blocking": any(i["severity"] == "error" for i in issues),
        "watertight": watertight,
        "as_given": as_given,
        "recommended": recommended,
        "min_wall_mm": None if min_wall_mm is None else round(min_wall_mm, 3),
        "thin_wall_fraction": round(thin_fraction, 4),
        "issues": issues,
    }


def _orient(
    mesh: trimesh.Trimesh,
    rotation_deg: tuple[float, float, float],
    printer: dict[str, Any],
    material: dict[str, Any],
) -> dict[str, Any]:
    rx, ry, rz = (math.radians(a) for a in rotation_deg)
    rot = _rotation(rx, ry, rz)
    verts: Floats = np.asarray(mesh.vertices, dtype=np.float64) @ rot.T
    normals: Floats = np.asarray(mesh.face_normals, dtype=np.float64) @ rot.T
    verts = verts - verts.min(axis=0)
    size = verts.max(axis=0)

    vol = printer["build_volume_mm"]
    fits_xy = bool(size[0] <= vol["x"] and size[1] <= vol["y"])
    fits_turned = bool(size[1] <= vol["x"] and size[0] <= vol["y"])
    fits_z = bool(size[2] <= vol["z"])

    areas: Floats = np.asarray(mesh.area_faces, dtype=np.float64)
    face_top = verts[:, 2][mesh.faces].max(axis=1)
    on_bed = (face_top < BED_EPS_MM) & (normals[:, 2] < -0.99)
    limit = -math.sin(math.radians(float(material["max_overhang_deg"])))
    overhang = (normals[:, 2] < limit) & ~on_bed

    return {
        "rotation_deg": dict(zip("xyz", map(float, rotation_deg), strict=True)),
        "size_mm": dict(zip("xyz", (round(float(s), 3) for s in size), strict=True)),
        "fits_bed": fits_z and (fits_xy or fits_turned),
        "rotate_z_90": fits_z and not fits_xy and fits_turned,
        "overhang_area_mm2": round(float(areas[overhang].sum()), 2),
        "bed_contact_area_mm2": round(float(areas[on_bed].sum()), 2),
    }


def _rotation(rx: float, ry: float, rz: float) -> Floats:
    """Rotate about X, then Y, then Z (static axes)."""
    cx, sx, cy, sy, cz, sz = (f(a) for a in (rx, ry, rz) for f in (math.cos, math.sin))
    x: Floats = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
    y: Floats = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    z: Floats = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
    rot: Floats = z @ y @ x
    return rot


def _wall_thickness(mesh: trimesh.Trimesh, samples: int, seed: int) -> Floats:
    """Distance from area-weighted surface samples, inward along the normal, to the far wall."""
    points, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    inward = -np.asarray(mesh.face_normals, dtype=np.float64)[face_idx]
    origins = np.asarray(points, dtype=np.float64) + inward * RAY_EPS_MM
    return _first_hit(np.asarray(mesh.triangles, dtype=np.float64), origins, inward) + RAY_EPS_MM


def _first_hit(tris: Floats, origins: Floats, dirs: Floats) -> Floats:
    """Möller-Trumbore, vectorised over rays x triangles. inf where a ray hits nothing."""
    v0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    out = np.full(len(origins), np.inf)
    step = max(1, RAY_CHUNK_ELEMENTS // max(1, len(tris)))
    for start in range(0, len(origins), step):
        o = origins[start : start + step, None, :]
        d = dirs[start : start + step, None, :]
        p = np.cross(d, e2[None])
        det = np.einsum("rtk,tk->rt", p, e1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - v0[None]
        u = np.einsum("rtk,rtk->rt", s, p) * inv
        q = np.cross(s, e1[None])
        v = np.einsum("rtk,rtk->rt", np.broadcast_to(d, q.shape), q) * inv
        t = np.einsum("rtk,tk->rt", q, e2) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > RAY_EPS_MM)
        out[start : start + step] = np.where(hit, t, np.inf).min(axis=1)
    return out


def _issues(
    watertight: bool,
    as_given: dict[str, Any],
    recommended: dict[str, Any],
    min_wall: float,
    nozzle: float,
    thin_fraction: float,
    too_thin_fraction: float,
    min_wall_mm: float | None,
    total_area: float,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def add(code: str, severity: str, message: str, fixes: list[str]) -> None:
        issues.append({"code": code, "severity": severity, "message": message, "fixes": fixes})

    if not watertight:
        add(
            "not_watertight",
            "error",
            "The model has holes or loose edges, so a slicer cannot tell inside from outside.",
            ["repair_mesh"],
        )

    if not as_given["fits_bed"]:
        size = as_given["size_mm"]
        dims = f"{size['x']:.0f} x {size['y']:.0f} x {size['z']:.0f} mm"
        if recommended["fits_bed"]:
            add(
                "exceeds_bed",
                "error",
                f"At {dims} it does not fit this printer as placed, but it fits if reoriented.",
                ["reorient", "split_for_bed"],
            )
        else:
            add(
                "exceeds_bed",
                "error",
                f"At {dims} it is larger than this printer can build in any orientation.",
                ["split_for_bed"],
            )

    if too_thin_fraction > THIN_FRACTION_LIMIT:
        add(
            "walls_too_thin",
            "error",
            f"Some walls are about {min_wall_mm:.2f} mm, thinner than the {nozzle:.2f} mm nozzle, "
            "so they will not print.",
            ["thicken_walls"],
        )
    elif thin_fraction > THIN_FRACTION_LIMIT:
        add(
            "thin_walls",
            "warning",
            f"Some walls are under {min_wall:.2f} mm and may be weak or print with gaps.",
            ["thicken_walls"],
        )

    overhang = as_given["overhang_area_mm2"]
    if overhang > max(OVERHANG_MIN_AREA_MM2, 0.01 * total_area):
        better = recommended["fits_bed"] and recommended["overhang_area_mm2"] < 0.5 * overhang
        add(
            "overhangs",
            "warning",
            f"About {overhang:.0f} mm² hangs over air and needs support"
            + (" unless the part is reoriented." if better else "."),
            ["reorient", "add_supports"] if better else ["add_supports"],
        )

    if as_given["fits_bed"] and as_given["bed_contact_area_mm2"] < SMALL_CONTACT_MM2:
        add(
            "small_bed_contact",
            "warning",
            "Very little of the part touches the bed, so it may come loose while printing.",
            ["reorient"]
            if recommended["bed_contact_area_mm2"] > as_given["bed_contact_area_mm2"]
            else [],
        )
    return issues
