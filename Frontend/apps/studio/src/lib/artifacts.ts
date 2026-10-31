import type { components } from "@kehora/api-client";
import type { PrintabilityReport, PrintFix } from "@kehora/types";

export type Artifact = components["schemas"]["ArtifactOut"];
export type Check = components["schemas"]["CheckOut"];

/** The mesh the viewer shows: the printable STL, if the build produced one. */
export function viewableMesh(artifacts: Artifact[]): Artifact | undefined {
  return artifacts.find((a) => a.format === "stl");
}

/** The printability engine's verdict for this version, with its full report. */
export function printability(
  checks: Check[],
): { status: string; report: PrintabilityReport } | undefined {
  const check = checks.find((c) => c.engine === "printability" && c.name === "printable");
  return check ? { status: check.status, report: check.report as unknown as PrintabilityReport } : undefined;
}

const FILE_LABELS: Record<string, string> = {
  stl: "Mesh for slicing (STL)",
  "3mf": "Print project (3MF)",
  step: "CAD model (STEP)",
  py: "Design script (build123d)",
  txt: "Log",
};

export function fileLabel(a: Artifact): string {
  return FILE_LABELS[a.format] ?? `${a.type}.${a.format}`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export const FIX_LABELS: Record<PrintFix, string> = {
  reorient: "Reorient",
  thicken_walls: "Thicken walls",
  add_supports: "Add supports",
  split_for_bed: "Split for the bed",
  repair_mesh: "Repair mesh",
};

/** "Turn it over (X 180°)" style hint when the best orientation differs from the delivered one. */
export function orientationHint(report: PrintabilityReport): string | undefined {
  const r = report.recommended.rotation_deg;
  const given = report.as_given.rotation_deg;
  if (r.x === given.x && r.y === given.y && r.z === given.z) return undefined;
  const turns = (["x", "y", "z"] as const)
    .filter((axis) => r[axis] !== 0)
    .map((axis) => `${r[axis]}° about ${axis.toUpperCase()}`);
  return `Prints best rotated ${turns.join(", ")}.`;
}
