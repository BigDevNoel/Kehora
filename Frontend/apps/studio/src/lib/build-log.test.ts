import type { RunEvent } from "@kehora/types";
import { describe, expect, it } from "vitest";

import { applyEvent, costLabel, initialBuildLog } from "./build-log";

let seq = 0;
function ev(type: RunEvent["type"], payload: Record<string, unknown> = {}, node?: string): RunEvent {
  seq += 1;
  return {
    run_id: "01a18b4a-0000-7000-8000-000000000000",
    seq,
    type,
    node: node ?? null,
    payload,
    created_at: "2026-10-30T12:00:00Z",
  };
}

const spec = { schema_version: 0, kind: "object", title: "Stand", summary: "A stand." };

describe("build log", () => {
  it("tracks the approval gate and finishes", () => {
    seq = 0;
    let s = initialBuildLog;
    for (const e of [
      ev("run_started"),
      ev("node_started", {}, "intake"),
      ev("cost_update", { cost_minor: 3 }),
      ev("needs_approval", { gate: "spec", spec }),
    ]) {
      s = applyEvent(s, e);
    }
    expect(s.awaitingApproval).toBe(true);
    expect(s.pendingSpec?.title).toBe("Stand");
    expect(costLabel(s)).toBe("$0.03");
    expect(s.lines.map((l) => l.text)).toContain("Understanding your request…");

    s = applyEvent(s, ev("node_started", {}, "create_version"));
    expect(s.awaitingApproval).toBe(false);
    s = applyEvent(s, ev("check_passed", { engine: "echo", name: "round_trip" }));
    s = applyEvent(s, ev("run_finished"));
    expect(s.finished).toBe(true);
    expect(s.lines.at(-1)?.tone).toBe("success");
  });

  it("ignores duplicates and never reports done with a failing check", () => {
    seq = 0;
    let s = applyEvent(initialBuildLog, ev("run_started"));
    const dup = { ...s.events[0]! };
    s = applyEvent(s, dup);
    expect(s.events).toHaveLength(1);
    s = applyEvent(s, ev("check_failed", { engine: "echo", name: "round_trip" }));
    s = applyEvent(s, ev("run_finished"));
    expect(s.finished).toBe(false);
  });

  it("records failures", () => {
    seq = 0;
    const s = applyEvent(applyEvent(initialBuildLog, ev("run_started")), ev("run_failed", { reason: "Spec rejected by user" }));
    expect(s.failure).toBe("Spec rejected by user");
  });
});
