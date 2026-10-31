import { describe, expect, it } from "vitest";

import { type Artifact, type Check, fileLabel, formatBytes, orientationHint, printability, viewableMesh } from "./artifacts";
import { report } from "./test-reports";

function artifact(name: string, format: string): Artifact {
  return { id: name, name, type: "mesh", format, size: 10, sha256: "0".repeat(64), created_at: "2026-10-31T00:00:00Z" };
}

describe("artifacts", () => {
  it("shows the STL in the viewer", () => {
    const files = [artifact("script.py", "py"), artifact("part.step", "step"), artifact("part.stl", "stl")];
    expect(viewableMesh(files)?.name).toBe("part.stl");
    expect(viewableMesh([artifact("echo.txt", "txt")])).toBeUndefined();
  });

  it("finds the printability verdict among the checks", () => {
    const checks: Check[] = [
      { id: "1", artifact_id: "a", engine: "cad", name: "watertight", status: "pass", report: {} },
      { id: "2", artifact_id: "a", engine: "printability", name: "printable", status: "warn", report: { ...report() } },
    ];
    expect(printability(checks)?.status).toBe("warn");
    expect(printability(checks)?.report.printer_id).toBe("prusa-mk4");
    expect(printability([])).toBeUndefined();
  });

  it("labels files in plain words", () => {
    expect(fileLabel(artifact("part.stl", "stl"))).toBe("Mesh for slicing (STL)");
    expect(fileLabel(artifact("odd.bin", "bin"))).toBe("mesh.bin");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });

  it("explains a better print orientation", () => {
    expect(orientationHint(report())).toBeUndefined();
    const flipped = report({ recommended: { ...report().recommended, rotation_deg: { x: 180, y: 0, z: 0 } } });
    expect(orientationHint(flipped)).toBe("Prints best rotated 180° about X.");
  });
});
