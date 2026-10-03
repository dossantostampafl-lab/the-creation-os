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

it("reports the local voice configuration returned by acknowledgement preloading", async () => {
  const { preloadVoiceAcknowledgement } = await import("./api");
  vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({
    detail: { code: "VOICE_MODELS_UNAVAILABLE", message: "Os modelos locais de voz não estão disponíveis.", nonretryable: true },
  }), { status: 503, headers: { "Content-Type": "application/json" } })));
  await expect(preloadVoiceAcknowledgement()).rejects.toThrow("modelos locais");
});

it("preserves a stable request identifier when sending a DEUS turn", async () => {
  const { converseWithDeus } = await import("./api");
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ response: "Olá" }), { status: 201, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  await converseWithDeus("conversation", "Oi", "11111111-1111-4111-8111-111111111111");
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).request_id).toBe("11111111-1111-4111-8111-111111111111");
});

it('filters knowledge searches by the selected project and reuses write identifiers', async () => {
  const { searchKnowledge, saveKnowledge } = await import('./api');
  const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({status:'empty',evidences:[]}),{status:200})));
  vi.stubGlobal('fetch',fetchMock);
  await searchKnowledge('Kokoro','project');
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({query:'Kokoro',project_id:'project'});
  await saveKnowledge('Voz','Kokoro','stable-id','project');
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({request_id:'stable-id',candidate:{title:'Voz',content:'Kokoro',project_id:'project'}});
});
