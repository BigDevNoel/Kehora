import { Badge, cn } from "@kehora/ui";
import { AlertTriangle, CheckCircle2, CircleDot, Loader2, XCircle } from "lucide-react";
import { useEffect, useRef } from "react";

import { type BuildLogState, costLabel, type Tone } from "../lib/build-log";

const ICONS: Record<Tone, typeof CircleDot> = {
  neutral: CircleDot,
  running: Loader2,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
};

const TONE_CLASS: Record<Tone, string> = {
  neutral: "text-muted-foreground",
  running: "text-primary",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
};

export function RunStatusBadge({ log }: { log: BuildLogState }) {
  if (log.failure) return <Badge variant="destructive">Stopped</Badge>;
  if (log.finished) return <Badge variant="success">Done</Badge>;
  if (log.awaitingApproval) return <Badge variant="warning">Needs your approval</Badge>;
  if (log.events.length) return <Badge variant="secondary">Building</Badge>;
  return <Badge variant="outline">Queued</Badge>;
}

export function BuildLog({ log }: { log: BuildLogState }) {
  const end = useRef<HTMLLIElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [log.lines.length]);

  return (
    <section aria-label="Build log" className="flex min-h-0 flex-col gap-2">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Build log</h2>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span data-testid="run-cost">{costLabel(log)}</span>
          <RunStatusBadge log={log} />
        </div>
      </header>
      <ol
        data-testid="build-log"
        aria-live="polite"
        className="min-h-0 flex-1 space-y-1 overflow-y-auto rounded-md border bg-muted/30 p-2 font-mono text-xs"
      >
        {log.lines.length === 0 && (
          <li className="text-muted-foreground">Waiting for the first step…</li>
        )}
        {log.lines.map((line, i) => {
          const Icon = ICONS[line.tone];
          const live = line.tone === "running" && i === log.lines.length - 1 && !log.awaitingApproval;
          return (
            <li
              key={line.seq}
              data-event-type={line.type}
              className={cn("flex items-start gap-2", TONE_CLASS[line.tone])}
            >
              <Icon className={cn("mt-0.5 size-3.5 shrink-0", live && "animate-spin")} aria-hidden />
              <span className="text-foreground">{line.text}</span>
            </li>
          );
        })}
        <li ref={end} aria-hidden />
      </ol>
    </section>
  );
}
