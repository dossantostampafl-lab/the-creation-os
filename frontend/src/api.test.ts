import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fetchSystemState, streamChronicle } from "./api";
beforeEach(() => {
  vi.stubGlobal("window", {
    localStorage: { getItem: () => "test-access" },
    sessionStorage: { getItem: () => null },
    location: { href: "https://creation.example/" }, setTimeout,
  });
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });
it("identifies the failing dashboard endpoint without exposing credentials", async () => {
  vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));
  await expect(fetchSystemState()).rejects.toThrow("/api/v1/system/state");
});
it("reconnects a terminated event stream from the last received position", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  const paths: string[] = [];
  const events: number[] = [];
  vi.stubGlobal("fetch", (url: string) => {
    paths.push(url);
    return Promise.resolve(new Response(new ReadableStream({ start(stream) {
      if (paths.length === 1) {
        stream.enqueue(new TextEncoder().encode('event: chronicle\ndata: {"position":42}\n\n'));
        stream.close();
      } else { controller.abort(); stream.close(); }
    } })));
  });
  const promise = streamChronicle(41, { onEvent: event => events.push(event.position), onResync: () => {}, onError: () => {} }, controller.signal);
  await vi.advanceTimersByTimeAsync(1200);
  expect(events).toEqual([42]);
  expect(paths[1]).toContain("after=42");
  controller.abort(); await promise;
});
