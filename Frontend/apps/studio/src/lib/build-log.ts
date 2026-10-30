import type { ProjectSpec, RunEvent } from "@kehora/types";

export type Tone = "neutral" | "running" | "success" | "warning" | "danger";

export interface LogLine {
  seq: number;
  type: RunEvent["type"];
  text: string;
  tone: Tone;
  at: string;
}

export interface BuildLogState {
  events: RunEvent[];
  lines: LogLine[];
  pendingSpec: ProjectSpec | null;
  awaitingApproval: boolean;
  finished: boolean;
  failure: string | null;
  costMinor: number;
  failingChecks: number;
}

export const initialBuildLog: BuildLogState = {
  events: [],
  lines: [],
  pendingSpec: null,
  awaitingApproval: false,
  finished: false,
  failure: null,
  costMinor: 0,
  failingChecks: 0,
};

const NODE_LABELS: Record<string, string> = {
  intake: "Understanding your request",
  spec: "Writing the spec",
  create_version: "Saving a new version",
  engine: "Running the engine in a sandbox",
};

function label(node: string | null | undefined): string {
  return (node && NODE_LABELS[node]) ?? node ?? "Step";
}

function money(minor: number, currency: string): string {
  return new Intl.NumberFormat("en", { style: "currency", currency }).format(minor / 100);
}

function describe(e: RunEvent): Omit<LogLine, "seq" | "type" | "at"> | null {
  const p = e.payload as Record<string, unknown>;
  switch (e.type) {
    case "run_started":
      return { text: "Build started", tone: "running" };
    case "node_started":
      return { text: `${label(e.node)}…`, tone: "running" };
    case "node_finished":
      return { text: `${label(e.node)}: done`, tone: "neutral" };
    case "needs_approval":
      return { text: "Spec ready. Review it and approve to continue.", tone: "warning" };
    case "artifact_created":
      return { text: `File created: ${String(p.format ?? "")} ${String(p.type ?? "")}`, tone: "neutral" };
    case "check_passed":
      return { text: `Check passed: ${String(p.engine)} · ${String(p.name)}`, tone: "success" };
    case "check_warned":
      return { text: `Check warning: ${String(p.engine)} · ${String(p.name)}`, tone: "warning" };
    case "check_failed":
      return { text: `Check failed: ${String(p.engine)} · ${String(p.name)}`, tone: "danger" };
    case "repair_attempt":
      return { text: "Fixing a failed check…", tone: "warning" };
    case "needs_input":
      return { text: "The agent needs more information.", tone: "warning" };
    case "cost_update":
      return null; // shown in the header, not as a log line
    case "run_finished":
      return { text: "Build finished. All checks passed.", tone: "success" };
    case "run_failed":
      return { text: `Build stopped: ${String(p.reason ?? "unknown error")}`, tone: "danger" };
    default:
      return null;
  }
}

/** Fold one event into the log. Events are applied once, in seq order. */
export function applyEvent(state: BuildLogState, e: RunEvent): BuildLogState {
  if (state.events.length > 0 && e.seq <= state.events[state.events.length - 1]!.seq) {
    return state;
  }
  const p = e.payload as Record<string, unknown>;
  const next: BuildLogState = { ...state, events: [...state.events, e] };
  const line = describe(e);
  if (line) next.lines = [...state.lines, { seq: e.seq, type: e.type, at: e.created_at, ...line }];

  switch (e.type) {
    case "needs_approval":
      next.awaitingApproval = true;
      next.pendingSpec = (p.spec as ProjectSpec | undefined) ?? null;
      break;
    case "node_started":
    case "run_failed":
      next.awaitingApproval = false;
      break;
    case "check_failed":
      next.failingChecks = state.failingChecks + 1;
      break;
    case "cost_update":
      next.costMinor = Number(p.cost_minor ?? state.costMinor);
      break;
    case "run_finished":
      // Never present "done" while a verifier is failing (CLAUDE.md).
      next.finished = state.failingChecks === 0;
      break;
  }
  if (e.type === "run_failed") next.failure = String(p.reason ?? "Build failed");
  return next;
}

export function costLabel(state: BuildLogState): string {
  return money(state.costMinor, "USD");
}
