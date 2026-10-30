import { afterEach, describe, expect, it, vi } from "vitest";

import { streamRunEvents } from "./index";

function sse(events: Array<{ seq: number; type: string }>): Response {
  const body = events
    .map((e) => {
      const data = JSON.stringify({ run_id: "r1", node: null, payload: {}, created_at: "", ...e });
      return `id: ${e.seq}\nevent: ${e.type}\ndata: ${data}\n\n`;
    })
    .join("");
  return new Response(new TextEncoder().encode(body), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("streamRunEvents", () => {
  it("reconnects with Last-Event-ID, skips duplicates and stops at the terminal event", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        sse([
          { seq: 1, type: "run_started" },
          { seq: 2, type: "node_started" },
        ]),
      )
      .mockResolvedValueOnce(
        sse([
          { seq: 2, type: "node_started" },
          { seq: 3, type: "run_finished" },
        ]),
      );
    vi.stubGlobal("fetch", fetchMock);

    const seen: number[] = [];
    await streamRunEvents({
      baseUrl: "http://api.test",
      runId: "r1",
      getToken: async () => "tok",
      onEvent: (e) => seen.push(e.seq),
    });

    expect(seen).toEqual([1, 2, 3]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [url, first] = fetchMock.mock.calls[0]!;
    expect(url).toBe("http://api.test/v1/runs/r1/events");
    expect(new Headers(first.headers).get("Authorization")).toBe("Bearer tok");
    expect(new Headers(fetchMock.mock.calls[1]![1].headers).get("Last-Event-ID")).toBe("2");
  });

  it("fails fast on 4xx", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 404 })));
    await expect(
      streamRunEvents({ baseUrl: "http://api.test", runId: "x", getToken: async () => null, onEvent: () => {} }),
    ).rejects.toThrow("404");
  });
});
