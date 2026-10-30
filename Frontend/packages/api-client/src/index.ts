// Hand-written wrapper over the generated OpenAPI types (src/generated/schema.ts, do not edit).
// Adds the Clerk bearer token to every request and a resumable SSE reader for run events.
import { fetchEventSource } from "@microsoft/fetch-event-source";
import createClient, { type Middleware } from "openapi-fetch";

import type { RunEvent } from "@kehora/types";

import type { components, paths } from "./generated/schema";

export type { components, paths };
export type Schemas = components["schemas"];
export type Project = Schemas["ProjectOut"];
export type ProjectDetail = Schemas["ProjectDetail"];
export type Run = Schemas["RunOut"];
export type Me = Schemas["MeOut"];

export type TokenGetter = () => Promise<string | null>;

export function createKehoraClient(baseUrl: string, getToken: TokenGetter) {
  const auth: Middleware = {
    async onRequest({ request }) {
      const token = await getToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
  };
  const client = createClient<paths>({ baseUrl });
  client.use(auth);
  return client;
}

export type KehoraClient = ReturnType<typeof createKehoraClient>;

const TERMINAL = new Set(["run_finished", "run_failed"]);

export interface StreamRunEventsOptions {
  baseUrl: string;
  runId: string;
  getToken: TokenGetter;
  onEvent: (event: RunEvent) => void;
  /** Resume after this seq (sent as Last-Event-ID). */
  lastSeq?: number;
  signal?: AbortSignal;
}

/**
 * Stream a run's events. Reconnects with Last-Event-ID after network errors, so every event is
 * delivered once and in order. Resolves after run_finished / run_failed.
 */
export async function streamRunEvents(opts: StreamRunEventsOptions): Promise<void> {
  let last = opts.lastSeq ?? 0;
  let done = false;
  const ctrl = new AbortController();
  opts.signal?.addEventListener("abort", () => ctrl.abort());

  await fetchEventSource(`${opts.baseUrl}/v1/runs/${opts.runId}/events`, {
    signal: ctrl.signal,
    openWhenHidden: true,
    async fetch(input, init) {
      const token = await opts.getToken();
      const headers = new Headers(init?.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (last > 0) headers.set("Last-Event-ID", String(last));
      return fetch(input, { ...init, headers });
    },
    async onopen(res) {
      if (!res.ok) throw new FatalStreamError(`events stream failed: ${res.status}`);
    },
    onmessage(msg) {
      if (!msg.data) return;
      const event = JSON.parse(msg.data) as RunEvent;
      if (event.seq <= last) return;
      last = event.seq;
      opts.onEvent(event);
      if (TERMINAL.has(event.type)) {
        done = true;
        ctrl.abort();
      }
    },
    onclose() {
      if (!done) throw new Error("stream closed early; reconnecting");
    },
    onerror(err) {
      if (err instanceof FatalStreamError) throw err;
      return 1000; // retry after 1 s
    },
  }).catch((err: unknown) => {
    if (!(done || ctrl.signal.aborted)) throw err;
  });
}

class FatalStreamError extends Error {}
