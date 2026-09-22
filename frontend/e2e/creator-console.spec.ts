import { expect, test } from "@playwright/test";

const state = {
  projection: "system",
  position: 1,
  generated_at: "2026-09-11T12:00:00Z",
  missions: [],
  tasks: [],
  universes: [],
  agents: [],
  memory: { conversation: 0, mission: 0, universe: 0, conscious: 0, total: 0 },
  pulse: {},
  counts: { missions: 0, running_missions: 0, tasks: 0, ready_tasks: 0, running_tasks: 0, failed_tasks: 0, active_universes: 0, active_agents: 0 },
};

async function mockDashboard(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/system/state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ chronicle_head: 1, projections: [] }) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ configured: true, configured_provider: "stub", providers: [{ provider: "stub", available: true, detail: null, models: [{ model: "stub-model", is_default: true, capabilities: ["text"], cost_tier: "UNKNOWN" }] }] }) }));
  await page.route("**/api/v1/system/events?after=1", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
}

test("Creator can start a conversation and receive a DEUS response", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await mockDashboard(page);
  await page.route("**/api/v1/conversations", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "conversation-1", creator_id: "creator-1", title: "Creator Session", status: "active", created_at: "2026-09-11T12:00:00Z", updated_at: "2026-09-11T12:00:00Z" }) });
    } else {
      await route.fallback();
    }
  });
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([
    { id: "m1", conversation_id: "conversation-1", actor_id: "creator-1", role: "creator", content: "Status?", route: "deus", metadata_json: {}, correlation_id: "c1", created_at: "2026-09-11T12:00:01Z" },
    { id: "m2", conversation_id: "conversation-1", actor_id: "deus", role: "deus", content: "System operational.", route: "deus", metadata_json: { provider: "stub" }, correlation_id: "c1", created_at: "2026-09-11T12:00:02Z" },
  ]) }));
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ message_id: "m1", conversation_id: "conversation-1", route: "deus", response: "System operational.", inception: null, system_state: null, correlation_id: "c1" }) }));

  await page.goto("/");
  await expect(page.getByRole("region", { name: "Creator Console" })).toBeVisible();
  await page.getByLabel("Message DEUS").fill("Status?");
  await page.getByRole("button", { name: "Send to DEUS" }).click();

  await expect(page.getByText("Status?", { exact: true })).toBeVisible();
  await expect(page.getByText("System operational.", { exact: true })).toBeVisible();
});

/** Fake speech engines: records what DEUS says and lets the test "say" things to it. */
async function installFakeSpeech(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    localStorage.setItem("creation_access_token", "e2e-token");
    const scope = window as unknown as Record<string, unknown>;
    const spoken: string[] = [];
    scope.__spoken = spoken;
    const synth = {
      getVoices: () => [],
      cancel: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      speak: (utterance: SpeechSynthesisUtterance) => {
        spoken.push(utterance.text);
        const fire = (name: "onstart" | "onboundary" | "onend") =>
          (utterance[name] as ((event: unknown) => void) | null)?.({ name: "word" });
        setTimeout(() => { fire("onstart"); fire("onboundary"); fire("onend"); }, 10);
      },
    };
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });

    type Fake = { running: boolean; onresult: ((event: unknown) => void) | null; onend: (() => void) | null };
    class FakeRecognition {
      running = false;
      onresult: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      onerror = null;
      start() { this.running = true; scope.__recognizer = this; }
      stop() { this.end(); }
      abort() { this.end(); }
      private end() { if (!this.running) return; this.running = false; this.onend?.(); }
    }
    for (const name of ["SpeechRecognition", "webkitSpeechRecognition"]) {
      Object.defineProperty(window, name, { value: FakeRecognition, configurable: true, writable: true });
    }
    scope.__say = (text: string) => {
      const recognizer = scope.__recognizer as Fake | undefined;
      if (!recognizer?.running) return false;
      const result = Object.assign([{ transcript: text }], { isFinal: true });
      recognizer.onresult?.({ resultIndex: 0, results: [result] });
      return true;
    };
  });
}

async function mockConversation(page: import("@playwright/test").Page, sent: string[]) {
  await page.route("**/api/v1/conversations", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "conversation-1" }) }));
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => {
    sent.push((route.request().postDataJSON() as { content: string }).content);
    return route.fulfill({ status: 201, contentType: "application/json", body: "{}" });
  });
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sent.length ? [
    { id: "m1", conversation_id: "conversation-1", actor_id: "creator-1", role: "creator", content: sent[sent.length - 1], route: "deus", metadata_json: {}, correlation_id: "c1", created_at: "2026-09-11T12:00:01Z" },
    { id: "m2", conversation_id: "conversation-1", actor_id: "deus", role: "deus", content: "**All** universes are breathing.", route: "deus", metadata_json: {}, correlation_id: "c1", created_at: "2026-09-11T12:00:02Z" },
  ] : []) }));
}

const spokenLines = (page: import("@playwright/test").Page) => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken);

test("DEUS falls back to the browser voice when ElevenLabs is not configured, and can be muted", async ({ page }) => {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ code: "VOICE_SYNTHESIS_DISABLED" }) }));
  const sent: string[] = [];
  await mockConversation(page, sent);

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Status?");
  await page.getByLabel("Message DEUS").press("Enter");

  await expect(page.getByText("**All** universes are breathing.", { exact: true })).toBeVisible();
  await expect.poll(() => spokenLines(page)).toEqual(["All universes are breathing."]);

  await page.getByRole("button", { name: "Mute DEUS voice" }).click();
  await expect(page.getByRole("button", { name: "Unmute DEUS voice" })).toBeVisible();
});

test("DEUS speaks with the ElevenLabs voice through the backend when it is configured", async ({ page }) => {
  await installFakeSpeech(page);
  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
      setTimeout(() => this.dispatchEvent(new Event("ended")), 50);
      return Promise.resolve();
    };
  });
  await mockDashboard(page);
  const synthesized: string[] = [];
  await page.route("**/api/v1/voice/synthesize", (route) => {
    synthesized.push((route.request().postDataJSON() as { text: string }).text);
    return route.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from("ID3-fake-mp3") });
  });
  const sent: string[] = [];
  await mockConversation(page, sent);

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Status?");
  await page.getByLabel("Message DEUS").press("Enter");

  await expect.poll(() => synthesized).toEqual(["All universes are breathing."]);
  expect(await spokenLines(page)).toEqual([]);
});

test("saying “Deus” wakes DEUS, which answers and then hears the request", async ({ page }) => {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 409, body: "{}" }));
  const sent: string[] = [];
  await mockConversation(page, sent);

  await page.goto("/");
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  await expect(page.getByText("Say “Deus” to call")).toBeVisible();

  await expect.poll(() => page.evaluate(() => (window as unknown as { __say: (t: string) => boolean }).__say("Deus"))).toBe(true);
  await expect.poll(() => spokenLines(page)).toEqual(["I'm here."]);

  await expect.poll(() => page.evaluate(() => (window as unknown as { __say: (t: string) => boolean }).__say("Status report"))).toBe(true);
  await expect.poll(() => sent).toEqual(["Status report"]);
  await expect.poll(() => spokenLines(page)).toEqual(["I'm here.", "All universes are breathing."]);
});

test("“Deus, <request>” in one breath goes straight to DEUS and ignores other speech", async ({ page }) => {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 409, body: "{}" }));
  const sent: string[] = [];
  await mockConversation(page, sent);

  await page.goto("/");
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  const say = (text: string) => page.evaluate((t) => (window as unknown as { __say: (t: string) => boolean }).__say(t), text);

  await expect.poll(() => say("adeus, see you tomorrow")).toBe(true);
  await expect.poll(() => say("Deus, how are the universes today?")).toBe(true);

  await expect.poll(() => sent).toEqual(["how are the universes today?"]);
  expect(await spokenLines(page)).not.toContain("I'm here.");
});

test("DEUS stops listening when nobody speaks after it is summoned", async ({ page }) => {
  await page.clock.install();
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 409, body: "{}" }));
  await mockConversation(page, []);

  await page.goto("/");
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  await expect(page.getByText("Say “Deus” to call")).toBeVisible();

  // Push-to-talk while the wake word is already listening must still time out.
  await page.getByRole("button", { name: "Talk to DEUS" }).click();
  await expect(page.getByRole("button", { name: "Stop listening" })).toBeVisible();
  await page.clock.runFor(9000);
  await expect(page.getByRole("button", { name: "Talk to DEUS" })).toBeVisible();
  await expect(page.getByText("Say “Deus” to call")).toBeVisible();
});

test("the microphone stays closed while DEUS has no configured inference", async ({ page }) => {
  await installFakeSpeech(page);
  await page.addInitScript(() => localStorage.setItem("creation_wake_word", "on"));
  await mockDashboard(page);
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ configured: false, configured_provider: "fake", providers: [] }) }));

  await page.goto("/");
  await expect(page.getByRole("button", { name: "Turn off “Deus” wake word" })).toBeDisabled();
  await page.waitForTimeout(500);
  expect(await page.evaluate(() => Boolean((window as unknown as { __recognizer?: { running: boolean } }).__recognizer?.running))).toBe(false);
  await expect(page.getByText("Say “Deus” to call")).toHaveCount(0);
});
