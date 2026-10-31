import { describe, expect, it } from "vitest";

import { distance, formatMm, formatSize, framingDistance, sectionHeight } from "./geometry";

describe("viewer geometry", () => {
  it("measures straight-line distance in mm", () => {
    expect(distance([0, 0, 0], [3, 4, 0])).toBe(5);
    expect(distance([1, 2, 3], [1, 2, 3])).toBe(0);
  });

  it("formats lengths to 0.1 mm without trailing zeros", () => {
    expect(formatMm(20)).toBe("20 mm");
    expect(formatMm(7.25)).toBe("7.3 mm");
    expect(formatMm(99.96)).toBe("100 mm");
    expect(formatMm(240.4)).toBe("240 mm");
  });

  it("formats a bounding box as X × Y × Z", () => {
    expect(formatSize({ x: 40, y: 30, z: 10 })).toBe("40 × 30 × 10 mm");
    expect(formatSize({ x: 150, y: 70.5, z: 3 })).toBe("150 × 70.5 × 3 mm");
  });

  it("clamps the section slider to the part height", () => {
    expect(sectionHeight(0.5, 40)).toBe(20);
    expect(sectionHeight(-1, 40)).toBe(0);
    expect(sectionHeight(2, 40)).toBe(40);
  });

  it("frames small parts at a minimum distance", () => {
    expect(framingDistance(5)).toBe(40);
    expect(framingDistance(100)).toBe(180);
  });
});
