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
  const messages: Array<Record<string, unknown>> = [];
  await page.exposeFunction("recordVoiceMessage", (text: string, role: string, turnId: number) => {
    messages.push({
      id: `${role}-${turnId}`,
      conversation_id: "conversation-1",
      actor_id: role,
      role,
      content: text,
      route: "deus",
      metadata_json: { voice: true, voice_turn_id: turnId },
      correlation_id: `turn-${turnId}`,
      created_at: new Date().toISOString(),
    });
  });
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
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(messages) }));
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
  const message = event as { type: string; text?: string; turn_id?: number };
  if (message.type === "transcript_commit" || message.type === "text_delta") {
    await page.evaluate(async ({ text, role, turnId }) => {
      const record = (window as unknown as {
        recordVoiceMessage: (text: string, role: string, turnId: number) => Promise<void>;
      }).recordVoiceMessage;
      await record(text, role, turnId);
    }, { text: message.text ?? "", role: message.type === "transcript_commit" ? "creator" : "deus", turnId: message.turn_id ?? 0 });
  }
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
  await expect.poll(async () => (await voiceSockets(page))[0].sent.some((raw) => JSON.parse(raw).type === "audio")).toBe(true);
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

test("FreeLLM provider is visible and reconnect uses a fresh single-use ticket", async ({ page }) => {
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
    provider: "freellmapi",
    text: "Resposta pelo provedor principal.",
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
    provider_selected: "freellmapi",
    fallback_reason: null,
    latency_ms: { transcript_to_first_token: 400 },
  });

  await expect(page.getByText("· freellmapi", { exact: true })).toBeVisible();

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

test("real audio enables speaking and canceled output cannot replace a follow-up", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);
  // Cancellation is driven by the explicit server event below. Chromium's fake
  // microphone emits a tone; mute it so that unrelated VAD does not cancel first.
  await page.addInitScript(() => {
    const getUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await getUserMedia(constraints);
      stream.getAudioTracks().forEach(track => { track.enabled = false; });
      return stream;
    };
  });
  await page.goto("/");
  await expect(page.getByText(/Pronto · diga “Deus”/)).toBeVisible();
  await serverSend(page, 0, { type: "transcript_commit", session_id: "session-1", turn_id: 1, text: "Olá" });
  await serverSend(page, 0, { type: "state", session_id: "session-1", turn_id: 1, state: "THINKING" });
  await serverSend(page, 0, { type: "audio_chunk", session_id: "session-1", turn_id: 1, audio_base64: "AAAAAA==" });
  await expect(page.getByText(/DEUS está falando/)).toBeVisible();
  await serverSend(page, 0, { type: "barge_in", session_id: "session-1", turn_id: 1, cancelled: true, state: "LISTENING" });
  await expect(page.getByText(/^Ouvindo/)).toBeVisible();
  await serverSend(page, 0, { type: "text_delta", session_id: "session-1", turn_id: 1, provider: "freellmapi", text: "Resposta cancelada" });
  await serverSend(page, 0, { type: "audio_chunk", session_id: "session-1", turn_id: 1, audio_base64: "AAAAAA==" });
  await expect(page.getByText("Resposta cancelada", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/^Ouvindo/)).toBeVisible();
  await serverSend(page, 0, { type: "transcript_commit", session_id: "session-1", turn_id: 2, text: "Continue" });
  await serverSend(page, 0, { type: "text_delta", session_id: "session-1", turn_id: 2, provider: "freellmapi", text: "Continuamos." });
  await expect(page.getByText("Continuamos.", { exact: true })).toBeVisible();
  await serverSend(page, 0, { type: "state", session_id: "old-session", turn_id: 99, state: "SPEAKING" });
  await expect(page.getByText(/DEUS está falando/)).toHaveCount(0);
});

test("reconnecting mid-reply preserves both exchanges when transport turn IDs restart", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);
  await page.goto("/");
  await expect(page.getByText(/Pronto · diga “Deus”/)).toBeVisible();
  await serverSend(page, 0, { type: "transcript_commit", session_id: "session-1", turn_id: 1, text: "Primeira pergunta" });
  await serverSend(page, 0, { type: "text_delta", session_id: "session-1", turn_id: 1, provider: "freellmapi", text: "Primeira resposta" });
  await page.evaluate(() => {
    (window as unknown as { __voiceSockets: Array<{ serverClose: () => void }> }).__voiceSockets[0].serverClose();
  });
  await expect.poll(async () => (await voiceSockets(page)).length).toBe(2);
  await expect(page.getByText(/Pronto · diga “Deus”/)).toBeVisible();
  await serverSend(page, 1, { type: "transcript_commit", session_id: "session-2", turn_id: 1, text: "Segunda pergunta" });
  await serverSend(page, 1, { type: "text_delta", session_id: "session-2", turn_id: 1, provider: "freellmapi", text: "Segunda resposta" });
  await expect(page.getByText("Primeira pergunta", { exact: true })).toBeVisible();
  await expect(page.getByText("Primeira resposta", { exact: true })).toBeVisible();
  await expect(page.getByText("Segunda pergunta", { exact: true })).toBeVisible();
  await expect(page.getByText("Segunda resposta", { exact: true })).toBeVisible();
});

test("local voice configuration failure stops the microphone and reconnect loop while typed chat works", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);
  await page.addInitScript(() => {
    const original = MediaStreamTrack.prototype.stop;
    Object.assign(window, { stoppedVoiceTracks: 0 });
    MediaStreamTrack.prototype.stop = function () {
      if (this.kind === "audio") (window as unknown as { stoppedVoiceTracks: number }).stoppedVoiceTracks += 1;
      return original.call(this);
    };
  });
  await page.route("**/api/v1/conversations/conversation-1/deus", route => route.fulfill({
    status: 201, contentType: "application/json", body: JSON.stringify({
      message_id: "creator-typed", conversation_id: "conversation-1", response: "Quatro.",
      route: "deus", inception: null, correlation_id: "typed-correlation",
    }),
  }));
  await page.goto("/");
  await expect(page.locator(".wake-hint")).toContainText("Pronto");
  await page.getByRole("textbox", { name: "Message DEUS" }).click();
  await expect.poll(async () => (await voiceSockets(page))[0]?.sent.some(raw => JSON.parse(raw).type === "audio")).toBeTruthy();
  await serverSend(page, 0, { type: "error", code: "VOICE_MODELS_UNAVAILABLE", message: "Os modelos locais de voz não estão disponíveis.", nonretryable: true });
  await page.evaluate(() => (window as unknown as { __voiceSockets: Array<{ serverClose: () => void }> }).__voiceSockets[0].serverClose());
  await expect(page.locator(".console-error")).toContainText("modelos locais");
  await expect.poll(() => page.evaluate(() => (window as unknown as { stoppedVoiceTracks: number }).stoppedVoiceTracks)).toBeGreaterThan(0);
  await page.waitForTimeout(1100);
  expect(ticketCalls.value).toBe(1);
  await page.getByRole("textbox", { name: "Message DEUS" }).fill("Quanto é dois mais dois?");
  await page.getByRole("button", { name: "Send to DEUS" }).click();
  await expect(page.locator(".console-message.deus-message").last()).toContainText("Quatro.");
});

test("configuration failure reported during microphone startup releases the pending audio stream", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);
  await page.addInitScript(() => {
    const Native = window.AudioContext;
    window.AudioContext = class extends Native {
      get state(): AudioContextState { return "suspended"; }
      resume(): Promise<void> { return new Promise(() => {}); }
    };
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    const scope = window as unknown as { releaseMicrophone?: () => void; pendingTrack?: MediaStreamTrack };
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await original(constraints);
      scope.pendingTrack = stream.getAudioTracks()[0];
      await new Promise<void>(resolve => { scope.releaseMicrophone = resolve; });
      return stream;
    };
  });
  await page.goto("/");
  await page.waitForFunction(() => Boolean((window as unknown as { releaseMicrophone?: () => void }).releaseMicrophone));
  await serverSend(page, 0, { type: "error", code: "VOICE_MODELS_UNAVAILABLE", message: "Os modelos locais de voz não estão disponíveis.", nonretryable: true });
  await page.evaluate(() => (window as unknown as { releaseMicrophone: () => void }).releaseMicrophone());
  await expect.poll(() => page.evaluate(() => (window as unknown as { pendingTrack: MediaStreamTrack }).pendingTrack.readyState)).toBe("ended");
  await expect(page.locator(".console-error")).toContainText("modelos locais");
});

test("configuration failure discovered while preloading acknowledgement remains visible without reconnecting", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);
  await page.route("**/api/v1/voice/session/acknowledgement", route => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({ detail: {
      code: "VOICE_MODELS_UNAVAILABLE", message: "Os modelos locais de voz não estão disponíveis.", nonretryable: true,
    } }),
  }));
  await page.goto("/");
  await expect(page.locator(".console-error")).toContainText("modelos locais");
  await page.waitForTimeout(1100);
  expect(ticketCalls.value).toBeLessThanOrEqual(1);
  await expect(page.locator(".wake-hint")).toContainText("precisa de atenção");
  await expect(page.getByRole("textbox", { name: "Message DEUS" })).toBeEnabled();
});


test("wake word recovers microphone capture after an initial permission/startup failure", async ({ page }) => {
  const ticketCalls = { value: 0 };
  await installVoiceSockets(page);
  await mockDashboard(page, ticketCalls);
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    let attempts = 0;
    navigator.mediaDevices.getUserMedia = async constraints => {
      attempts += 1;
      if (attempts === 1) throw new DOMException("gesture required", "NotAllowedError");
      return original(constraints);
    };
    Object.assign(window, { voiceMediaAttempts: () => attempts });
  });

  await page.goto("/");
  await expect(page.locator(".console-error")).toContainText("gesture required");
  await expect(page.locator(".wake-hint")).toContainText("precisa de atenção");

  await page.getByRole("textbox", { name: "Message DEUS" }).click();

  await expect.poll(() => page.evaluate(() =>
    (window as unknown as { voiceMediaAttempts: () => number }).voiceMediaAttempts()
  )).toBeGreaterThanOrEqual(2);
  await expect.poll(async () =>
    (await voiceSockets(page))[0]?.sent.some(raw => JSON.parse(raw).type === "audio")
  ).toBeTruthy();
  await expect(page.locator(".wake-hint")).toContainText("Pronto");
  await expect(page.locator(".console-error")).toHaveCount(0);
});
