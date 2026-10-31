import type { PrintabilityReport } from "@kehora/types";

const orientation = {
  rotation_deg: { x: 0, y: 0, z: 0 },
  size_mm: { x: 40, y: 30, z: 10 },
  fits_bed: true,
  rotate_z_90: false,
  overhang_area_mm2: 0,
  bed_contact_area_mm2: 1200,
};

/** A clean report for a 40 x 30 x 10 mm part; tests override what they need. */
export function report(overrides: Partial<PrintabilityReport> = {}): PrintabilityReport {
  return {
    printer_id: "prusa-mk4",
    material_id: "pla",
    blocking: false,
    watertight: true,
    as_given: orientation,
    recommended: orientation,
    min_wall_mm: 2.4,
    thin_wall_fraction: 0,
    issues: [],
    ...overrides,
  };
}
