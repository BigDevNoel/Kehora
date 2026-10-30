import { streamRunEvents } from "@kehora/api-client";
import { useEffect, useReducer } from "react";

import { useApi } from "../api";
import { env } from "../env";
import { applyEvent, type BuildLogState, initialBuildLog } from "./build-log";
import type { RunEvent } from "@kehora/types";

type Action = { kind: "event"; event: RunEvent } | { kind: "reset" };

function reducer(state: BuildLogState, action: Action): BuildLogState {
  return action.kind === "reset" ? initialBuildLog : applyEvent(state, action.event);
}

/** Live build log for a run: replays history, then streams until the run ends. */
export function useRunEvents(runId: string | undefined, onTerminal?: () => void): BuildLogState {
  const { getToken } = useApi();
  const [state, dispatch] = useReducer(reducer, initialBuildLog);

  useEffect(() => {
    dispatch({ kind: "reset" });
    if (!runId) return;
    const ctrl = new AbortController();
    streamRunEvents({
      baseUrl: env.apiUrl,
      runId,
      getToken,
      signal: ctrl.signal,
      onEvent: (event) => {
        dispatch({ kind: "event", event });
        if (event.type === "run_finished" || event.type === "run_failed") onTerminal?.();
        if (event.type === "needs_approval") onTerminal?.();
      },
    }).catch((err: unknown) => console.error("run event stream failed", err));
    return () => ctrl.abort();
    // onTerminal is intentionally not a dependency: it must not restart the stream.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, getToken]);

  return state;
}
