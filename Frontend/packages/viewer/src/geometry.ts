// Pure helpers for the 3D viewer: no three.js or WebGL, so they unit-test in jsdom.

export type Vec3 = readonly [number, number, number];

export function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

/** Number in mm to 0.1 mm, without a trailing ".0": 20, 7.3, 240. */
export function formatNumber(mm: number): string {
  const rounded = mm < 100 ? Math.round(mm * 10) / 10 : Math.round(mm);
  return String(rounded);
}

export function formatMm(mm: number): string {
  return `${formatNumber(mm)} mm`;
}

export function formatSize(size: { x: number; y: number; z: number }): string {
  return `${formatNumber(size.x)} × ${formatNumber(size.y)} × ${formatNumber(size.z)} mm`;
}

/** Height of the section plane for a 0..1 slider over a part of the given height. */
export function sectionHeight(fraction: number, height: number): number {
  return Math.min(1, Math.max(0, fraction)) * height;
}

/** Camera distance that frames a part whose largest side is `largest` mm, at least 40 mm. */
export function framingDistance(largest: number): number {
  return Math.max(40, largest * 1.8);
}
