import { expect, test } from "@playwright/test";

const state = {
  projection: "system",
  position: 1,
  generated_at: "2026-09-30T12:00:00Z",
  missions: [], tasks: [], universes: [], agents: [],
  memory: { conversation: 0, mission: 0, universe: 0, conscious: 0, total: 0 },
  pulse: {},
  counts: {
    missions: 0, running_missions: 0, tasks: 0, ready_tasks: 0,
    running_tasks: 0, failed_tasks: 0, active_universes: 0, active_agents: 0,
  },
  pagination: {
    page: 1, page_size: 25, has_next: false,
    totals: { missions: 0, tasks: 0, universes: 0, agents: 0 },
  },
};

async function installVoiceSocket(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    localStorage.setItem("creation_access_token", "e2e-token");
    localStorage.setItem("creation_conversation_id", "conversation-1");

    const scope = window as unknown as {
      __voiceSocket?: FakeWebSocket;
      __voiceUrls?: string[];
      __voiceSent?: string[];
      __voiceServer?: (event: object) => boolean;
    };

    class FakeWebSocket {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSING = 2;
      static readonly CLOSED = 3;
      readonly url: string;
      readyState = FakeWebSocket.OPEN;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;
      onopen: ((event: Event) => void) | null = null;

      constructor(url: string) {
        this.url = url;
        scope.__voiceSocket = this;
        (scope.__voiceUrls ??= []).push(url);
        setTimeout(() => {
          this.onmessage?.(new MessageEvent("message", {
            data: JSON.stringify({
              type: "session_ready",
              session_id: "voice-session-1",
              turn_id: 0,
              state: "ARMED",
              creator_id: "creator-1",
            }),
          }));
        }, 25);
      }

      send(payload: string) {
        (scope.__voiceSent ??= []).push(payload);
      }

      close() {
        this.readyState = FakeWebSocket.CLOSED;
      }

      addEventListener() {}
      removeEventListener() {}
      dispatchEvent() { return true; }
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      writable: true,
      value: FakeWebSocket,
    });
    scope.__voiceServer = (event: object) => {
      const socket = scope.__voiceSocket;
      if (!socket?.onmessage) return false;
      socket.onmessage(new MessageEvent("message", { data: JSON.stringify(event) }));
      return true;
    };
  });
}

async function mockDashboard(
  page: import("@playwright/test").Page,
  inferenceConfigured = true,
) {
  await page.route(/\/api\/v1\/system\/state(?:\?.*)?$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ chronicle_head: 1, projections: [] }) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/system/inference", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(inferenceConfigured
        ? {
            configured: true,
            configured_provider: "freellmapi",
            providers: [{ provider: "freellmapi", available: true, detail: null, models: [] }],
          }
        : { configured: false, configured_provider: "fake", providers: [] }),
    }));
  await page.route("**/api/v1/system/events?after=1", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/inceptions", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/voice/session/ticket", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ ticket: "voice-ticket-1" }),
    }));
}

test("realtime DEUS voice is always armed without push-to-talk or browser speech recognition", async ({ page }) => {
  await installVoiceSocket(page);
  await mockDashboard(page);

  await page.goto("/");

  await expect(page.getByText("Pronto · diga “Deus”", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Talk to DEUS|Stop listening|wake word/i })).toHaveCount(0);

  const socketInfo = await page.evaluate(() => {
    const scope = window as unknown as { __voiceUrls?: string[] };
    return (scope.__voiceUrls ?? []).filter((url) => url.includes("/api/v1/voice/session"));
  });
  expect(socketInfo).toHaveLength(1);
  const url = new URL(socketInfo[0]);
  expect(url.protocol).toBe("ws:");
  expect(url.pathname).toBe("/api/v1/voice/session");
  expect(url.searchParams.get("ticket")).toBe("voice-ticket-1");
  expect(url.searchParams.get("conversation_id")).toBe("conversation-1");
  expect(socketInfo[0]).not.toContain("e2e-token");

  await page.evaluate(() => (window as unknown as { __voiceServer: (event: object) => boolean }).__voiceServer({
    type: "wake_detected",
    session_id: "voice-session-1",
    turn_id: 1,
    acknowledge: true,
  }));
  await page.evaluate(() => (window as unknown as { __voiceServer: (event: object) => boolean }).__voiceServer({
    type: "transcript_commit",
    session_id: "voice-session-1",
    turn_id: 1,
    text: "como está o projeto?",
  }));
  await page.evaluate(() => (window as unknown as { __voiceServer: (event: object) => boolean }).__voiceServer({
    type: "state",
    session_id: "voice-session-1",
    turn_id: 1,
    state: "THINKING",
  }));
  await page.evaluate(() => (window as unknown as { __voiceServer: (event: object) => boolean }).__voiceServer({
    type: "text_delta",
    session_id: "voice-session-1",
    turn_id: 1,
    provider: "freellmapi",
    text: "Estou ",
  }));
  await page.evaluate(() => (window as unknown as { __voiceServer: (event: object) => boolean }).__voiceServer({
    type: "text_delta",
    session_id: "voice-session-1",
    turn_id: 1,
    provider: "freellmapi",
    text: "aqui.",
  }));

  await expect(page.getByText("como está o projeto?", { exact: true })).toBeVisible();
  await expect(page.getByText("Estou aqui.", { exact: true })).toBeVisible();
  await expect(page.getByText("Pensando…", { exact: true })).toBeVisible();

  await page.evaluate(() => (window as unknown as { __voiceServer: (event: object) => boolean }).__voiceServer({
    type: "state",
    session_id: "voice-session-1",
    turn_id: 1,
    state: "LISTENING",
  }));
  await page.evaluate(() => (window as unknown as { __voiceServer: (event: object) => boolean }).__voiceServer({
    type: "telemetry",
    session_id: "voice-session-1",
    turn_id: 1,
    provider_selected: "freellmapi",
    latency_ms: { transcript_to_first_token: 420 },
  }));

  await expect(page.getByText("Ouvindo…", { exact: true })).toBeVisible();
  await expect(page.getByText(/freellmapi/)).toBeVisible();
});

test("voice session stays closed when no inference provider is available", async ({ page }) => {
  await installVoiceSocket(page);
  await mockDashboard(page, false);

  await page.goto("/");

  await expect(page.getByPlaceholder("Configure um provedor de inferência para falar com DEUS.")).toBeVisible();
  const urls = await page.evaluate(() =>
    ((window as unknown as { __voiceUrls?: string[] }).__voiceUrls ?? [])
      .filter((url) => url.includes("/api/v1/voice/session")));
  expect(urls).toEqual([]);
});
