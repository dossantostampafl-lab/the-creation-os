import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const state = {
  projection: "system",
  position: 1,
  generated_at: "2026-09-30T22:00:00Z",
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

async function installVoiceSockets(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("creation_access_token", "e2e-token");
    localStorage.setItem("creation_conversation_id", "conversation-1");

    type FakeScope = Window & {
      __voiceSockets?: FakeWebSocket[];
    };
    const scope = window as FakeScope;
    let voiceCount = 0;

    class FakeWebSocket {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSING = 2;
      static readonly CLOSED = 3;
      readonly url: string;
      readonly sent: string[] = [];
      readonly voice: boolean;
      readyState = FakeWebSocket.OPEN;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onclose: ((event: CloseEvent) => void) | null = null;

      constructor(url: string | URL) {
        this.url = String(url);
        this.voice = this.url.includes("/api/v1/voice/session");
        if (this.voice) {
          voiceCount += 1;
          (scope.__voiceSockets ??= []).push(this);
          const sessionId = `session-${voiceCount}`;
          setTimeout(() => {
            this.onmessage?.(new MessageEvent("message", {
              data: JSON.stringify({
                type: "session_ready",
                session_id: sessionId,
                creator_id: "creator-1",
                turn_id: 0,
                state: "ARMED",
              }),
            }));
          }, 20);
        }
      }

      send(payload: string) {
        this.sent.push(payload);
      }

      close() {
        if (this.readyState === FakeWebSocket.CLOSED) return;
        this.readyState = FakeWebSocket.CLOSED;
        this.onclose?.(new CloseEvent("close", { code: 1000 }));
      }

      serverSend(event: object) {
        this.onmessage?.(new MessageEvent("message", {
          data: JSON.stringify(event),
        }));
      }

      serverClose() {
        this.close();
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
  });
}

async function mockDashboard(page: Page, ticketCalls: { value: number }) {
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
      body: JSON.stringify({
        configured: true,
        configured_provider: "freellmapi",
        providers: [{ provider: "freellmapi", available: true, detail: null, models: [] }],
      }),
    }));
  await page.route("**/api/v1/system/events?after=1", (route) =>
    route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/inceptions", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/voice/session/acknowledgement", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      headers: {
        "X-DEUS-Audio-Format": "pcm_s16le",
        "X-DEUS-Audio-Sample-Rate": "24000",
      },
      body: Buffer.from([0, 0, 0, 0]),
    }));
  await page.route("**/api/v1/voice/session/ticket", (route) => {
    ticketCalls.value += 1;
    return route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ ticket: `ticket-${ticketCalls.value}` }),
    });
  });
}

async function voiceSockets(page: Page) {
  return page.evaluate(() => {
    const sockets = (window as unknown as { __voiceSockets?: Array<{ url: string; sent: string[] }> }).__voiceSockets ?? [];
    return sockets.map((socket) => ({ url: socket.url, sent: socket.sent }));
  });
}

async function serverSend(page: Page, index: number, event: object) {
  await page.evaluate(({ index, event }) => {
    const sockets = (window as unknown as { __voiceSockets?: Array<{ serverSend: (event: object) => void }> }).__voiceSockets ?? [];
    sockets[index]?.serverSend(event);
  }, { index, event });
}

test("realtime DEUS carries five continuous pt-BR turns without a microphone button", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);

  await page.goto("/");
  await expect.poll(async () => (await voiceSockets(page)).length).toBe(1);
  await expect(page.getByText(/Pronto · diga “Deus”/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Talk to DEUS|wake word|microphone/i })).toHaveCount(0);

  await serverSend(page, 0, {
    type: "wake_detected",
    session_id: "session-1",
    turn_id: 0,
    acknowledge: true,
  });

  for (let turnId = 1; turnId <= 5; turnId += 1) {
    const creator = turnId === 1 ? "Como está o projeto?" : `Continuação ${turnId}?`;
    const deus = turnId === 1
      ? "O projeto está operacional."
      : `Seguimos normalmente no turno ${turnId}.`;

    await serverSend(page, 0, {
      type: "transcript_commit",
      session_id: "session-1",
      turn_id: turnId,
      text: creator,
    });
    await expect(page.getByText(creator, { exact: true })).toBeVisible();

    await serverSend(page, 0, {
      type: "state",
      session_id: "session-1",
      turn_id: turnId,
      state: "THINKING",
    });
    await expect(page.getByText(/Pensando/)).toBeVisible();

    await serverSend(page, 0, {
      type: "text_delta",
      session_id: "session-1",
      turn_id: turnId,
      provider: "freellmapi",
      text: deus,
    });
    await expect(page.getByText(deus, { exact: true })).toBeVisible();

    await serverSend(page, 0, {
      type: "state",
      session_id: "session-1",
      turn_id: turnId,
      state: "LISTENING",
    });
    await serverSend(page, 0, {
      type: "telemetry",
      session_id: "session-1",
      turn_id: turnId,
      provider_selected: "freellmapi",
      fallback_reason: null,
      latency_ms: { transcript_to_first_token: 120, first_token_to_audio: 80 },
    });
    await expect(page.getByText(/Ouvindo/)).toBeVisible();
  }

  await expect(page.getByText("O projeto está operacional.", { exact: true })).toBeVisible();
  expect(ticketCalls.value).toBe(1);
});

test("Klaus fallback is visible and reconnect uses a fresh single-use ticket", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);

  await page.goto("/");
  await expect.poll(async () => (await voiceSockets(page)).length).toBe(1);
  await expect(page.getByText(/Pronto · diga “Deus”/)).toBeVisible();

  await serverSend(page, 0, {
    type: "transcript_commit",
    session_id: "session-1",
    turn_id: 1,
    text: "Responda.",
  });
  await serverSend(page, 0, {
    type: "state",
    session_id: "session-1",
    turn_id: 1,
    state: "THINKING",
  });
  await serverSend(page, 0, {
    type: "text_delta",
    session_id: "session-1",
    turn_id: 1,
    provider: "klaus",
    text: "Resposta pela reserva.",
  });
  await serverSend(page, 0, {
    type: "state",
    session_id: "session-1",
    turn_id: 1,
    state: "LISTENING",
  });
  await serverSend(page, 0, {
    type: "telemetry",
    session_id: "session-1",
    turn_id: 1,
    provider_selected: "klaus",
    fallback_reason: "primary_failure_or_first_token_timeout",
    latency_ms: { transcript_to_first_token: 400 },
  });

  await expect(page.getByText(/klaus/i)).toBeVisible();

  await page.evaluate(() => {
    const sockets = (window as unknown as { __voiceSockets?: Array<{ serverClose: () => void }> }).__voiceSockets ?? [];
    sockets[0]?.serverClose();
  });

  await expect.poll(() => ticketCalls.value, { timeout: 10_000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(async () => (await voiceSockets(page)).length, { timeout: 10_000 }).toBeGreaterThanOrEqual(2);

  const sockets = await voiceSockets(page);
  expect(new URL(sockets[1].url).searchParams.get("ticket")).toBe("ticket-2");
  expect(sockets[1].url).not.toContain("e2e-token");
});
