import { existsSync, readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { expect, test } from "@playwright/test";

type WorkerEvent = Record<string, unknown>;
type WorkerListeners = Record<string, (event: WorkerEvent) => void>;

function loadWorker() {
  const path = new URL("../public/sw.js", import.meta.url);
  if (!existsSync(path)) return { listeners: {} as WorkerListeners, skipWaitingCalls: () => 0, resolveCachePuts: () => undefined };

  const listeners: WorkerListeners = {};
  let skipWaitingCount = 0;
  const pendingCachePuts: Array<() => void> = [];
  const cache = {
    addAll: async () => undefined,
    put: () => new Promise<void>((resolve) => pendingCachePuts.push(resolve)),
  };
  const caches = {
    open: async () => cache,
    keys: async () => ["creation-static-old", "unrelated-cache"],
    delete: async () => true,
    match: async () => undefined,
  };
  const self = {
    location: { origin: "https://creation.example" },
    clients: { claim: async () => undefined },
    skipWaiting: async () => { skipWaitingCount += 1; },
    addEventListener: (type: string, listener: WorkerListeners[string]) => { listeners[type] = listener; },
  };
  const fetch = async () => new Response("network", { status: 200 });
  runInNewContext(readFileSync(path, "utf8"), { self, caches, fetch, URL, Request, Response, Promise, console });
  return {
    listeners,
    skipWaitingCalls: () => skipWaitingCount,
    resolveCachePuts: () => pendingCachePuts.splice(0).forEach((resolve) => resolve()),
  };
}

function dispatchFetch(listener: WorkerListeners[string] | undefined, request: Request) {
  let response: Promise<Response> | undefined;
  listener?.({ request, respondWith: (value: Promise<Response>) => { response = value; } });
  return response;
}

test("service worker registers the complete lifecycle", () => {
  const { listeners } = loadWorker();
  expect(Object.keys(listeners)).toEqual(expect.arrayContaining(["install", "activate", "fetch", "message"]));
});

test("service worker leaves sensitive and external traffic network-only", () => {
  const { listeners } = loadWorker();
  const requests = [
    new Request("https://creation.example/api/v1/system/state"),
    new Request("https://creation.example/assets/app.js", { headers: { Authorization: "Bearer secret" } }),
    new Request("https://creation.example/mission", { method: "POST" }),
    new Request("https://outside.example/assets/app.js"),
  ];
  for (const request of requests) expect(dispatchFetch(listeners.fetch, request), request.url).toBeUndefined();
});

test("service worker handles same-origin static assets", () => {
  const { listeners } = loadWorker();
  expect(dispatchFetch(listeners.fetch, new Request("https://creation.example/assets/app.123.js"))).toBeInstanceOf(Promise);
});

test("service worker keeps cache writes inside the response lifetime", async () => {
  const { listeners, resolveCachePuts } = loadWorker();
  const response = dispatchFetch(listeners.fetch, new Request("https://creation.example/assets/app.123.js"));
  const beforeCacheWrite = await Promise.race([
    response?.then(() => "response"),
    new Promise<string>((resolve) => setTimeout(() => resolve("pending"), 10)),
  ]);
  expect(beforeCacheWrite).toBe("pending");

  resolveCachePuts();
  await expect(response).resolves.toBeInstanceOf(Response);
});

test("service worker activates only after an explicit update message", () => {
  const { listeners, skipWaitingCalls } = loadWorker();
  listeners.message?.({ data: { type: "IGNORED" } });
  expect(skipWaitingCalls()).toBe(0);
  listeners.message?.({ data: { type: "SKIP_WAITING" } });
  expect(skipWaitingCalls()).toBe(1);
});
