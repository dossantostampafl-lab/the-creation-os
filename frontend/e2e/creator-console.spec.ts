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
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
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
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, contentType: "application/json", body: JSON.stringify({ detail: "ElevenLabs voice synthesis is disabled" }) }));
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
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
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
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
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
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
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

test("typing while DEUS listens keeps the typed text and ends listening", async ({ page }) => {
  await page.clock.install();
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
  await mockConversation(page, []);

  await page.goto("/");
  await page.getByRole("button", { name: "Talk to DEUS" }).click();
  await expect(page.getByRole("button", { name: "Stop listening" })).toBeVisible();

  await page.getByLabel("Message DEUS").fill("typed by hand");
  await expect(page.getByRole("button", { name: "Talk to DEUS" })).toBeVisible();
  await page.clock.runFor(9000);
  await expect(page.getByLabel("Message DEUS")).toHaveValue("typed by hand");
});

test("after “Deus” the conversation continues without the wake word until goodbye", async ({ page }) => {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
  const sent: string[] = [];
  await mockConversation(page, sent);
  const say = (text: string) => page.evaluate((t) => (window as unknown as { __say: (t: string) => boolean }).__say(t), text);

  await page.goto("/");
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();

  await expect.poll(() => say("Deus")).toBe(true);
  await expect.poll(() => spokenLines(page)).toEqual(["I'm here."]);
  await expect.poll(() => say("Status report")).toBe(true);
  await expect.poll(() => sent).toEqual(["Status report"]);
  await expect(page.getByText("In conversation — say “bye” to end")).toBeVisible();

  // No wake word needed for the follow-up.
  await expect.poll(() => spokenLines(page)).toHaveLength(2);
  await expect.poll(() => say("And the missions?")).toBe(true);
  await expect.poll(() => sent).toEqual(["Status report", "And the missions?"]);

  await expect.poll(() => spokenLines(page)).toHaveLength(3);
  await expect.poll(() => say("tchau")).toBe(true);
  await expect.poll(() => spokenLines(page)).toEqual(["I'm here.", "All universes are breathing.", "All universes are breathing.", "Goodbye."]);
  expect(sent).toEqual(["Status report", "And the missions?"]);
  await expect(page.getByText("Say “Deus” to call")).toBeVisible();
});

const proposal = {
  id: "inception-1",
  conversation_id: "conversation-1",
  title: "Landing page",
  description: "Publish a landing page.",
  status: "awaiting_creator_decision",
  proposed_at: "2026-09-11T12:00:02Z",
  trinity_assessment: {
    sophia: { opportunities: ["Reach visitors"], risks: ["Copy needs review"], recommendation: "Start with one simple page." },
    rockmam: { objective: "Publish a landing page.", constraints: [], completion_criteria: [] },
    mission_plan: { strategy: "Write, then build.", steps: [
      { step_key: "build", title: "Build the page", universe: "WEB", position: 2 },
      { step_key: "write", title: "Write the copy", universe: "CONTENT", position: 1 },
    ] },
    verdict: { result: "REQUIRES_CREATOR", unavailable_universes: ["WEB"] },
  },
};

async function mockTrinity(page: import("@playwright/test").Page, sent: string[], decisions: string[]) {
  await mockConversation(page, sent);
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => {
    sent.push((route.request().postDataJSON() as { content: string }).content);
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
      response: "SOPHIA and ROCKMAM propose a landing page.",
      inception: { id: "inception-1", title: "Landing page", status: "awaiting_creator_decision", verdict: "REQUIRES_CREATOR" },
    }) });
  });
  await page.route("**/api/v1/inceptions/inception-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(proposal) }));
  for (const [decision, status] of [["approve", "approved"], ["reject", "rejected"]]) {
    await page.route(`**/api/v1/inceptions/inception-1/${decision}`, (route) => {
      decisions.push(decision);
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...proposal, status }) });
    });
  }
}

test("a Mission request shows the Trinity proposal, which the Creator can approve", async ({ page }) => {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
  const sent: string[] = [];
  const decisions: string[] = [];
  await mockTrinity(page, sent, decisions);

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Build a landing page");
  await page.getByLabel("Message DEUS").press("Enter");

  const card = page.getByRole("article", { name: "Trinity proposal: Landing page" });
  await expect(card).toBeVisible();
  await expect(card.getByText("Needs WEB")).toBeVisible();
  await expect(card.getByText("Start with one simple page.")).toBeVisible();
  await expect(card.getByText("Risks: Copy needs review")).toBeVisible();
  await expect(card.getByRole("listitem")).toHaveText(["Write the copy CONTENT", "Build the page WEB"]);

  await card.getByRole("button", { name: "Approve" }).click();
  await expect(card.getByText("Approved")).toBeVisible();
  await expect(card.getByRole("button", { name: "Approve" })).toHaveCount(0);
  expect(decisions).toEqual(["approve"]);
});

test("in a voice conversation, “sim, aprova” approves the pending proposal instead of messaging DEUS", async ({ page }) => {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
  const sent: string[] = [];
  const decisions: string[] = [];
  await mockTrinity(page, sent, decisions);
  const say = (text: string) => page.evaluate((t) => (window as unknown as { __say: (t: string) => boolean }).__say(t), text);

  await page.goto("/");
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  await expect.poll(() => say("Deus, build a landing page")).toBe(true);
  await expect(page.getByRole("article", { name: "Trinity proposal: Landing page" })).toBeVisible();

  await expect.poll(() => spokenLines(page)).toHaveLength(1);
  await expect.poll(() => say("sim, aprova")).toBe(true);
  await expect.poll(() => decisions).toEqual(["approve"]);
  await expect.poll(() => spokenLines(page)).toEqual(["All universes are breathing.", "Inception approved."]);
  expect(sent).toEqual(["build a landing page"]);
});

test("a spoken decision answers the newest proposal, not an older one still pending", async ({ page }) => {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.addInitScript(() => localStorage.setItem("creation_conversation_id", "conversation-1"));
  const older = { ...proposal, id: "inception-0", title: "Older idea", proposed_at: "2026-09-10T08:00:00Z" };
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([older]) }));
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
  const sent: string[] = [];
  const decisions: string[] = [];
  await mockTrinity(page, sent, decisions);
  await page.route("**/api/v1/inceptions/inception-0/approve", (route) => {
    decisions.push("approve-older");
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...older, status: "approved" }) });
  });
  const say = (text: string) => page.evaluate((t) => (window as unknown as { __say: (t: string) => boolean }).__say(t), text);

  await page.goto("/");
  await expect(page.getByRole("article", { name: "Trinity proposal: Older idea" })).toBeVisible();
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  await expect.poll(() => say("Deus, build a landing page")).toBe(true);
  await expect(page.getByRole("article", { name: "Trinity proposal: Landing page" })).toBeVisible();

  await expect.poll(() => spokenLines(page)).toHaveLength(1);
  await expect.poll(() => say("aprova")).toBe(true);
  await expect.poll(() => decisions).toEqual(["approve"]);
});
