import { expect, test } from "@playwright/test";
import type { Page, WebSocketRoute } from "@playwright/test";

const state = {
  projection: "system",
  position: 1,
  generated_at: "2026-09-30T22:00:00Z",
  missions: [], tasks: [], universes: [], agents: [],
  memory: { conversation: 0, mission: 0, universe: 0, conscious: 0, total: 0 },
  pulse: {},
  counts: { missions: 0, running_missions: 0, tasks: 0, ready_tasks: 0, running_tasks: 0, failed_tasks: 0, active_universes: 0, active_agents: 0 },
  pagination: { page: 1, page_size: 25, has_next: false, totals: { missions: 0, tasks: 0, universes: 0, agents: 0 } },
};

type Message = {
  id: string;
  conversation_id: string;
  actor_id: string;
  role: string;
  content: string;
  route: string;
  metadata_json: Record<string, unknown>;
  correlation_id: string;
  created_at: string;
};

async function mockDashboard(page: Page, messages: Message[], ticketCalls: { value: number }) {
  await page.addInitScript(() => {
    localStorage.setItem("creation_access_token", "e2e-token");
    localStorage.setItem("creation_conversation_id", "conversation-1");
  });
  await page.route(/\/api\/v1\/system\/state(?:\?.*)?$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ chronicle_head: 1, projections: [] }) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      configured: true,
      configured_provider: "freellmapi",
      providers: [{ provider: "freellmapi", available: true, detail: null, models: [{ model: "auto", is_default: true, capabilities: ["text", "streaming"], cost_tier: "UNKNOWN" }] }],
    }),
  }));
  await page.route("**/api/v1/system/events?after=1", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(messages) }));
  await page.route("**/api/v1/voice/session/ticket", (route) => {
    ticketCalls.value += 1;
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ticket: `ticket-${ticketCalls.value}` }) });
  });
}

function appendCanonical(messages: Message[], turnId: number, creator: string, deus: string, provider: string) {
  const created = `2026-09-30T22:00:${String(turnId).padStart(2, "0")}Z`;
  messages.push(
    {
      id: `creator-${turnId}`,
      conversation_id: "conversation-1",
      actor_id: "creator-1",
      role: "creator",
      content: creator,
      route: "deus",
      metadata_json: { voice: true },
      correlation_id: `c-${turnId}`,
      created_at: created,
    },
    {
      id: `deus-${turnId}`,
      conversation_id: "conversation-1",
      actor_id: "deus",
      role: "deus",
      content: deus,
      route: "deus",
      metadata_json: { voice: true, provider },
      correlation_id: `c-${turnId}`,
      created_at: created,
    },
  );
}

test("realtime DEUS voice wakes once and carries five continuous pt-BR turns without microphone buttons", async ({ page }) => {
  const messages: Message[] = [];
  const ticketCalls = { value: 0 };
  await mockDashboard(page, messages, ticketCalls);

  let socket: WebSocketRoute | null = null;
  let sessionCount = 0;
  const clientEvents: string[] = [];
  await page.routeWebSocket(/\/api\/v1\/voice\/session\?/, (ws) => {
    socket = ws;
    sessionCount += 1;
    const sessionId = `session-${sessionCount}`;
    ws.onMessage((message) => {
      clientEvents.push(String(message));
    });
    setTimeout(() => ws.send(JSON.stringify({
      type: "session_ready",
      session_id: sessionId,
      creator_id: "creator-1",
      turn_id: 0,
      state: "ARMED",
    })), 10);
  });

  await page.goto("/");
  await expect(page.getByText(/Pronto · diga “Deus”/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Talk to DEUS|wake word|microphone/i })).toHaveCount(0);
  await expect.poll(() => clientEvents.some((raw) => JSON.parse(raw).type === "audio"), { timeout: 10_000 }).toBe(true);

  const active = () => {
    if (!socket) throw new Error("voice websocket not connected");
    return socket;
  };

  active().send(JSON.stringify({ type: "wake_detected", session_id: "session-1", turn_id: 1, acknowledge: true }));
  await expect(page.getByText(/Pronto · diga “Deus”|Ouvindo/)).toBeVisible();

  for (let turnId = 1; turnId <= 5; turnId += 1) {
    const creator = turnId === 1 ? "Como está o projeto?" : `Continuação ${turnId}?`;
    const deus = turnId === 1 ? "O projeto está operacional." : `Seguimos normalmente no turno ${turnId}.`;

    active().send(JSON.stringify({ type: "transcript_commit", session_id: "session-1", turn_id: turnId, text: creator }));
    await expect(page.getByText(creator, { exact: true })).toBeVisible();

    active().send(JSON.stringify({ type: "state", session_id: "session-1", turn_id: turnId, state: "THINKING" }));
    await expect(page.getByText(/Pensando/)).toBeVisible();

    active().send(JSON.stringify({ type: "text_delta", session_id: "session-1", turn_id: turnId, provider: "freellmapi", text: deus }));
    await expect(page.getByText(deus, { exact: true })).toBeVisible();

    active().send(JSON.stringify({ type: "state", session_id: "session-1", turn_id: turnId, state: "SPEAKING" }));
    active().send(JSON.stringify({ type: "audio_chunk", session_id: "session-1", turn_id: turnId, audio_base64: "AAAAAA==" }));
    appendCanonical(messages, turnId, creator, deus, "freellmapi");
    active().send(JSON.stringify({ type: "state", session_id: "session-1", turn_id: turnId, state: "LISTENING" }));
    active().send(JSON.stringify({
      type: "telemetry",
      session_id: "session-1",
      turn_id: turnId,
      provider_selected: "freellmapi",
      fallback_reason: null,
      latency_ms: { transcript_to_first_token: 120, first_token_to_audio: 80 },
    }));
    await expect(page.getByText(/Ouvindo/)).toBeVisible();
  }

  await expect(page.getByText("O projeto está operacional.", { exact: true })).toBeVisible();
  expect(messages.filter((message) => message.role === "creator")).toHaveLength(5);
});

test("realtime session exposes Klaus fallback and reconnects with a fresh single-use ticket", async ({ page }) => {
  const messages: Message[] = [];
  const ticketCalls = { value: 0 };
  await mockDashboard(page, messages, ticketCalls);

  const sockets: WebSocketRoute[] = [];
  await page.routeWebSocket(/\/api\/v1\/voice\/session\?/, (ws) => {
    sockets.push(ws);
    const sessionId = `session-${sockets.length}`;
    setTimeout(() => ws.send(JSON.stringify({
      type: "session_ready",
      session_id: sessionId,
      creator_id: "creator-1",
      turn_id: 0,
      state: "ARMED",
    })), 10);
  });

  await page.goto("/");
  await expect.poll(() => sockets.length).toBe(1);
  await expect(page.getByText(/Pronto · diga “Deus”/)).toBeVisible();

  sockets[0].send(JSON.stringify({ type: "transcript_commit", session_id: "session-1", turn_id: 1, text: "Responda." }));
  sockets[0].send(JSON.stringify({ type: "state", session_id: "session-1", turn_id: 1, state: "THINKING" }));
  sockets[0].send(JSON.stringify({ type: "text_delta", session_id: "session-1", turn_id: 1, provider: "klaus", text: "Resposta pela reserva." }));
  appendCanonical(messages, 1, "Responda.", "Resposta pela reserva.", "klaus");
  sockets[0].send(JSON.stringify({ type: "state", session_id: "session-1", turn_id: 1, state: "LISTENING" }));
  sockets[0].send(JSON.stringify({
    type: "telemetry",
    session_id: "session-1",
    turn_id: 1,
    provider_selected: "klaus",
    fallback_reason: "primary_failure_or_first_token_timeout",
    latency_ms: { transcript_to_first_token: 400 },
  }));

  await expect(page.getByText(/klaus/i)).toBeVisible();
  sockets[0].close();
  await expect.poll(() => ticketCalls.value, { timeout: 10_000 }).toBeGreaterThanOrEqual(2);
  await expect.poll(() => sockets.length, { timeout: 10_000 }).toBeGreaterThanOrEqual(2);
  await expect(page.getByText(/Pronto · diga “Deus”|Reconectando/)).toBeVisible();
});
