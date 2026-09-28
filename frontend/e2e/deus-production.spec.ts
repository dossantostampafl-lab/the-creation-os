import { expect, test } from "@playwright/test";

const state = {
  projection: "system",
  position: 1,
  generated_at: "2026-09-28T06:00:00Z",
  missions: [], tasks: [], universes: [], agents: [],
  memory: { conversation: 0, mission: 0, universe: 0, conscious: 0, total: 0 },
  pulse: {},
  counts: { missions: 0, running_missions: 0, tasks: 0, ready_tasks: 0, running_tasks: 0, failed_tasks: 0, active_universes: 0, active_agents: 0 },
  pagination: { page: 1, page_size: 25, has_next: false, totals: { missions: 0, tasks: 0, universes: 0, agents: 0 } },
};

async function mockStaticDashboard(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ chronicle_head: 1, projections: [] }) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ configured: true, configured_provider: "stub", providers: [{ provider: "stub", available: true, detail: null, models: [] }] }) }));
  await page.route("**/api/v1/system/events?after=1", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
}

test("an expired access token is refreshed once and DEUS chat keeps working", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("creation_access_token", "expired-access");
    localStorage.setItem("creation_conversation_id", "conversation-1");
    sessionStorage.setItem("creation_refresh_token", "refresh-1");
  });

  let refreshes = 0;
  await page.route("**/api/v1/auth/refresh", (route) => {
    refreshes += 1;
    expect(route.request().headers().authorization).toBe("Bearer refresh-1");
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: "fresh-access", refresh_token: "refresh-2", token_type: "bearer", expires_in: 15 }) });
  });
  await page.route(/\/api\/v1\/system\/state(?:\?.*)?$/, (route) => {
    const auth = route.request().headers().authorization;
    return route.fulfill(auth === "Bearer fresh-access"
      ? { status: 200, contentType: "application/json", body: JSON.stringify(state) }
      : { status: 401, contentType: "application/json", body: "{}" });
  });
  await mockStaticDashboard(page);
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => {
    expect(route.request().headers().authorization).toBe("Bearer fresh-access");
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ message_id: "m1", conversation_id: "conversation-1", route: "deus", response: "Estou aqui.", inception: null, correlation_id: "c1" }) });
  });
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, contentType: "application/json", body: "{}" }));

  await page.goto("/");
  await expect(page.getByText("LIVE", { exact: true })).toBeVisible();
  await page.getByLabel("Message DEUS").fill("Deus, está me ouvindo?");
  await page.getByRole("button", { name: "Send to DEUS" }).click();
  await expect(page.getByText("Estou aqui.", { exact: true })).toBeVisible();
  expect(refreshes).toBe(1);
  await expect(page.evaluate(() => sessionStorage.getItem("creation_refresh_token"))).resolves.toBe("refresh-2");
});

test("wake acknowledgement uses the configured DEUS voice instead of an arbitrary browser voice", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("creation_access_token", "e2e-token");
    localStorage.setItem("creation_wake_word_v3", "on");
    const scope = window as unknown as Record<string, unknown>;
    const spoken: string[] = [];
    scope.__spoken = spoken;
    Object.defineProperty(window, "speechSynthesis", { configurable: true, value: {
      getVoices: () => [], cancel: () => {}, addEventListener: () => {}, removeEventListener: () => {},
      speak: (utterance: SpeechSynthesisUtterance) => { spoken.push(utterance.text); setTimeout(() => utterance.onend?.(new SpeechSynthesisEvent("end")), 5); },
    } });
    class FakeRecognition {
      running = false;
      onresult: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      start() { this.running = true; scope.__recognizer = this; }
      stop() { this.running = false; this.onend?.(); }
      abort() { this.stop(); }
    }
    Object.defineProperty(window, "SpeechRecognition", { configurable: true, value: FakeRecognition });
    Object.defineProperty(window, "webkitSpeechRecognition", { configurable: true, value: FakeRecognition });
    scope.__say = (text: string) => {
      const r = scope.__recognizer as FakeRecognition | undefined;
      if (!r?.running) return false;
      const result = Object.assign([{ transcript: text, confidence: 0.99 }], { isFinal: true });
      r.onresult?.({ resultIndex: 0, results: [result] });
      return true;
    };
    HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
      setTimeout(() => this.dispatchEvent(new Event("ended")), 10);
      return Promise.resolve();
    };
  });
  await page.route(/\/api\/v1\/system\/state(?:\?.*)?$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await mockStaticDashboard(page);
  await page.route("**/api/v1/conversations", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "conversation-1" }) }));
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  const synthesized: string[] = [];
  await page.route("**/api/v1/voice/synthesize", (route) => {
    synthesized.push((route.request().postDataJSON() as { text: string }).text);
    return route.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from("ID3-fake") });
  });

  await page.goto("/");
  await expect.poll(() => page.evaluate(() => (window as unknown as { __say: (text: string) => boolean }).__say("Deus"))).toBe(true);
  await expect.poll(() => synthesized).toEqual(["Estou aqui."]);
  expect(await page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken)).toEqual([]);
});
