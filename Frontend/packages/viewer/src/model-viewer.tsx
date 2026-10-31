// STL viewer (PRD 8.1): orbit and zoom, a print bed, a horizontal section plane and a two-click
// measure tool. Millimetres, Z up, part resting on the bed at z = 0 as the CAD engine exports it.
// Import it lazily (`@kehora/viewer/model`) so three.js stays out of the studio's first bundle.

import { Bounds, Grid, Html, Line, OrbitControls } from "@react-three/drei";
import { Canvas, type ThreeEvent, useLoader } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import { type BufferGeometry, DoubleSide, Object3D, Plane, Vector3 } from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";

import { distance, formatMm, formatSize, framingDistance, sectionHeight, type Vec3 } from "./geometry";

Object3D.DEFAULT_UP.set(0, 0, 1);

export interface ModelViewerProps {
  /** Signed URL of a binary or ASCII STL. */
  url: string;
  className?: string;
}

type Tool = "orbit" | "measure";

interface Placed {
  geometry: BufferGeometry;
  size: { x: number; y: number; z: number };
}

function usePlacedGeometry(url: string): Placed {
  const raw = useLoader(STLLoader, url);
  return useMemo(() => {
    const geometry = raw.clone();
    geometry.computeBoundingBox();
    const box = geometry.boundingBox!;
    // Centre on the bed in X/Y and rest on z = 0.
    geometry.translate(-(box.min.x + box.max.x) / 2, -(box.min.y + box.max.y) / 2, -box.min.z);
    geometry.computeVertexNormals();
    const size = { x: box.max.x - box.min.x, y: box.max.y - box.min.y, z: box.max.z - box.min.z };
    return { geometry, size };
  }, [raw]);
}

function Part({
  placed,
  clip,
  onPick,
}: {
  placed: Placed;
  clip: Plane | null;
  onPick: (point: Vec3) => void;
}) {
  return (
    <mesh
      geometry={placed.geometry}
      castShadow
      onClick={(e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        onPick([e.point.x, e.point.y, e.point.z]);
      }}
    >
      <meshStandardMaterial
        color="#7c9cbf"
        metalness={0.1}
        roughness={0.6}
        side={DoubleSide}
        clippingPlanes={clip ? [clip] : []}
      />
    </mesh>
  );
}

function Measurement({ points }: { points: Vec3[] }) {
  if (points.length === 0) return null;
  const [a, b] = points;
  return (
    <group>
      {points.map((p, i) => (
        <mesh key={i} position={p as unknown as Vector3}>
          <sphereGeometry args={[0.8, 16, 16]} />
          <meshBasicMaterial color="#e11d48" />
        </mesh>
      ))}
      {a && b && (
        <>
          <Line points={[a, b] as unknown as Vector3[]} color="#e11d48" lineWidth={2} />
          <Html position={[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2]} center>
            <span
              data-testid="measure-label"
              className="rounded bg-background/90 px-1.5 py-0.5 text-xs font-medium whitespace-nowrap shadow"
            >
              {formatMm(distance(a, b))}
            </span>
          </Html>
        </>
      )}
    </group>
  );
}

function Scene({
  url,
  tool,
  section,
  points,
  setPoints,
  onSize,
}: {
  url: string;
  tool: Tool;
  section: number | null;
  points: Vec3[];
  setPoints: (p: Vec3[]) => void;
  onSize: (size: Placed["size"]) => void;
}) {
  const placed = usePlacedGeometry(url);
  useEffect(() => onSize(placed.size), [placed.size, onSize]);
  const largest = Math.max(placed.size.x, placed.size.y, placed.size.z);
  const clip = useMemo(
    () =>
      section === null
        ? null
        : new Plane(new Vector3(0, 0, -1), sectionHeight(section, placed.size.z)),
    [section, placed.size.z],
  );
  const d = framingDistance(largest);
  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[d, -d, d * 1.5]} intensity={1.2} castShadow />
      <directionalLight position={[-d, d, d]} intensity={0.4} />
      {/* Frames the part on load and on "Reset view" (the Canvas remounts). */}
      <Bounds fit clip margin={1.4}>
        <Part
          placed={placed}
          clip={clip}
          onPick={(p) => {
            if (tool !== "measure") return;
            setPoints(points.length >= 2 ? [p] : [...points, p]);
          }}
        />
      </Bounds>
      <Measurement points={points} />
      <Grid
        rotation={[Math.PI / 2, 0, 0]}
        cellSize={10}
        sectionSize={50}
        infiniteGrid
        fadeDistance={d * 6}
        cellColor="#94a3b8"
        sectionColor="#64748b"
      />
      <OrbitControls makeDefault target={[0, 0, placed.size.z / 2]} />
    </>
  );
}

export function ModelViewer({ url, className }: ModelViewerProps) {
  const [tool, setTool] = useState<Tool>("orbit");
  const [section, setSection] = useState<number | null>(null);
  const [points, setPoints] = useState<Vec3[]>([]);
  const [size, setSize] = useState<Placed["size"] | null>(null);
  const [view, setView] = useState(0);

  return (
    <div className={`relative flex min-h-80 flex-1 flex-col overflow-hidden rounded-lg border ${className ?? ""}`}>
      <div className="flex flex-wrap items-center gap-2 border-b bg-muted/40 p-2 text-xs" role="toolbar" aria-label="Viewer tools">
        <button
          type="button"
          aria-pressed={tool === "measure"}
          className="rounded border px-2 py-1 aria-pressed:bg-primary aria-pressed:text-primary-foreground"
          onClick={() => {
            setTool(tool === "measure" ? "orbit" : "measure");
            setPoints([]);
          }}
        >
          Measure
        </button>
        <button
          type="button"
          aria-pressed={section !== null}
          className="rounded border px-2 py-1 aria-pressed:bg-primary aria-pressed:text-primary-foreground"
          onClick={() => setSection(section === null ? 0.5 : null)}
        >
          Section
        </button>
        {section !== null && (
          <label className="flex items-center gap-1">
            <span className="sr-only">Section height</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={section}
              onChange={(e) => setSection(Number(e.target.value))}
              aria-label="Section height"
            />
            {size && <span>{formatMm(sectionHeight(section, size.z))}</span>}
          </label>
        )}
        <button
          type="button"
          className="rounded border px-2 py-1"
          onClick={() => {
            setView(view + 1);
            setPoints([]);
          }}
        >
          Reset view
        </button>
        {size && (
          <span data-testid="model-size" className="ml-auto text-muted-foreground">
            {formatSize(size)}
          </span>
        )}
      </div>
      {tool === "measure" && (
        <p className="absolute top-12 left-2 z-10 rounded bg-background/90 px-2 py-1 text-xs shadow">
          Click two points on the part.
        </p>
      )}
      <Canvas
        key={view}
        shadows
        gl={{ localClippingEnabled: true, preserveDrawingBuffer: true }}
        camera={{ position: [120, -160, 120], fov: 40, near: 0.1, far: 10000 }}
        className="flex-1"
        data-testid="model-canvas"
      >
        <Scene url={url} tool={tool} section={section} points={points} setPoints={setPoints} onSize={setSize} />
      </Canvas>
    </div>
  );
}

export default ModelViewer;
