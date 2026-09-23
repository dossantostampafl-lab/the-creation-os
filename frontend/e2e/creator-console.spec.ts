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

const assessment = {
  sophia: { opportunities: ["Reach visitors"], risks: ["Copy needs review"], recommendation: "Start with one simple page." },
  rockmam: { objective: "Publish a landing page.", constraints: [], completion_criteria: [] },
  mission_plan: { strategy: "Write, then build.", steps: [
    { step_key: "build", title: "Build the page", universe: "web", position: 2 },
    { step_key: "write", title: "Write the copy", universe: "content", position: 1 },
  ] },
};

const readyInception = {
  id: "inception-1",
  conversation_id: "conversation-1",
  title: "Landing page",
  description: "Publish a landing page.",
  status: "approved",
  proposed_at: "2026-09-11T12:00:02Z",
  trinity_assessment: { ...assessment, verdict: { result: "VIABLE", blockers: [], unavailable_universes: [] }, mission_id: "mission-1" },
};

const blockedInception = {
  ...readyInception,
  status: "awaiting_creator_decision",
  trinity_assessment: {
    ...assessment,
    verdict: { result: "REQUIRES_CREATOR", blockers: [{ universe: "web", reason: "inactive" }], unavailable_universes: ["web"] },
  },
};

type Calls = string[];

/** DEUS answers every request with the given Trinity proposal; the Mission behind it keeps its state. */
async function mockTrinity(page: import("@playwright/test").Page, sent: string[], calls: Calls,
  inception: typeof readyInception | typeof blockedInception = readyInception) {
  await mockConversation(page, sent);
  const missions: Record<string, string> = { "mission-0": "validated", "mission-1": "validated" };
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => {
    sent.push((route.request().postDataJSON() as { content: string }).content);
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
      response: "ROCKMAM prepared the Mission.",
      inception: { id: inception.id, title: inception.title, status: inception.status, verdict: inception.trinity_assessment.verdict.result },
    }) });
  });
  await page.route("**/api/v1/inceptions/inception-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(inception) }));
  await page.route("**/api/v1/missions/*", (route) => {
    const id = route.request().url().split("/").pop() ?? "";
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id, inception_id: "inception-1", title: "Landing page", objective: "Publish a landing page.", status: missions[id] }) });
  });
  await page.route("**/api/v1/missions/*/start", (route) => {
    const id = route.request().url().split("/").at(-2) ?? "";
    calls.push(`start ${id}`);
    missions[id] = "executing";
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id, inception_id: "inception-1", title: "Landing page", objective: "Publish a landing page.", status: "executing" }) });
  });
  for (const [decision, status] of [["cancel", "cancelled"], ["reject", "rejected"]]) {
    await page.route(`**/api/v1/inceptions/inception-1/${decision}`, (route) => {
      calls.push(decision);
      missions["mission-1"] = "cancelled";
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...inception, status }) });
    });
  }
}

const say = (page: import("@playwright/test").Page, text: string) =>
  page.evaluate((t) => (window as unknown as { __say: (t: string) => boolean }).__say(t), text);

async function setUp(page: import("@playwright/test").Page) {
  await installFakeSpeech(page);
  await mockDashboard(page);
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 501, body: "{}" }));
}

test("ROCKMAM delivers a viable Mission ready to start, and the Creator authorizes it", async ({ page }) => {
  await setUp(page);
  const sent: string[] = [];
  const calls: Calls = [];
  await mockTrinity(page, sent, calls);

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Build a landing page");
  await page.getByLabel("Message DEUS").press("Enter");

  const card = page.getByRole("article", { name: "Trinity proposal: Landing page" });
  await expect(card.getByText("MISSION READY")).toBeVisible();
  await expect(card.getByText("Viable")).toBeVisible();
  await expect(card.getByText("Start with one simple page.")).toBeVisible();
  await expect(card.getByRole("listitem")).toHaveText(["Write the copy content", "Build the page web"]);

  await card.getByRole("button", { name: "Authorize & start" }).click();
  await expect(card.getByText("Executing")).toBeVisible();
  await expect(card.getByRole("button", { name: "Authorize & start" })).toHaveCount(0);
  expect(calls).toEqual(["start mission-1"]);
});

test("in a voice conversation, “pode iniciar” starts the prepared Mission instead of messaging DEUS", async ({ page }) => {
  await setUp(page);
  const sent: string[] = [];
  const calls: Calls = [];
  await mockTrinity(page, sent, calls);

  await page.goto("/");
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  await expect.poll(() => say(page, "Deus, build a landing page")).toBe(true);
  await expect(page.getByRole("article", { name: "Trinity proposal: Landing page" }).getByText("MISSION READY")).toBeVisible();

  await expect.poll(() => spokenLines(page)).toHaveLength(1);
  await expect.poll(() => say(page, "pode iniciar")).toBe(true);
  await expect.poll(() => calls).toEqual(["start mission-1"]);
  await expect.poll(() => spokenLines(page)).toEqual(["All universes are breathing.", "Mission authorized. Starting."]);
  expect(sent).toEqual(["build a landing page"]);
});

test("“cancela” drops the prepared Mission", async ({ page }) => {
  await setUp(page);
  const sent: string[] = [];
  const calls: Calls = [];
  await mockTrinity(page, sent, calls);

  await page.goto("/");
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  await expect.poll(() => say(page, "Deus, build a landing page")).toBe(true);
  const card = page.getByRole("article", { name: "Trinity proposal: Landing page" });
  await expect(card.getByText("MISSION READY")).toBeVisible();

  await expect.poll(() => spokenLines(page)).toHaveLength(1);
  await expect.poll(() => say(page, "cancela")).toBe(true);
  await expect.poll(() => calls).toEqual(["cancel"]);
  await expect(card.getByText("Cancelled")).toBeVisible();
  await expect.poll(() => spokenLines(page)).toEqual(["All universes are breathing.", "Mission cancelled."]);
});

test("a spoken go starts the newest Mission, not an older one still waiting", async ({ page }) => {
  await setUp(page);
  await page.addInitScript(() => localStorage.setItem("creation_conversation_id", "conversation-1"));
  const older = { ...readyInception, id: "inception-0", title: "Older idea", proposed_at: "2026-09-10T08:00:00Z",
    trinity_assessment: { ...readyInception.trinity_assessment, mission_id: "mission-0" } };
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([older]) }));
  const sent: string[] = [];
  const calls: Calls = [];
  await mockTrinity(page, sent, calls);

  await page.goto("/");
  await expect(page.getByRole("article", { name: "Trinity proposal: Older idea" }).getByText("MISSION READY")).toBeVisible();
  await page.getByRole("button", { name: "Turn on “Deus” wake word" }).click();
  await expect.poll(() => say(page, "Deus, build a landing page")).toBe(true);
  await expect(page.getByRole("article", { name: "Trinity proposal: Landing page" })).toBeVisible();

  await expect.poll(() => spokenLines(page)).toHaveLength(1);
  await expect.poll(() => say(page, "autoriza")).toBe(true);
  await expect.poll(() => calls).toEqual(["start mission-1"]);
});

test("a plan ROCKMAM cannot staff says what is missing and can only be dismissed", async ({ page }) => {
  await setUp(page);
  const sent: string[] = [];
  const calls: Calls = [];
  await mockTrinity(page, sent, calls, blockedInception);

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Build a landing page");
  await page.getByLabel("Message DEUS").press("Enter");

  const card = page.getByRole("article", { name: "Trinity proposal: Landing page" });
  await expect(card.getByText("NOT VIABLE YET")).toBeVisible();
  await expect(card.getByText("Universe web is not active")).toBeVisible();
  await expect(card.getByRole("button", { name: "Authorize & start" })).toHaveCount(0);

  await card.getByRole("button", { name: "Dismiss" }).click();
  await expect(card.getByText("Dismissed")).toBeVisible();
  expect(calls).toEqual(["reject"]);
});

test("a Mission whose start stopped halfway is cancelled on the Mission, and old proposals still render", async ({ page }) => {
  await setUp(page);
  await page.addInitScript(() => localStorage.setItem("creation_conversation_id", "conversation-1"));
  const halfStarted = { ...readyInception, id: "inception-0", title: "Half started", proposed_at: "2026-09-10T08:00:00Z",
    trinity_assessment: { ...readyInception.trinity_assessment, mission_id: "mission-0" } };
  const legacy = { ...blockedInception, id: "inception-9", title: "Legacy proposal",
    trinity_assessment: { ...assessment, verdict: { result: "REQUIRES_CREATOR", unavailable_universes: ["web"] } } };
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([halfStarted, legacy]) }));
  const sent: string[] = [];
  const calls: Calls = [];
  await mockTrinity(page, sent, calls);
  await page.route("**/api/v1/missions/mission-0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "mission-0", inception_id: "inception-0", title: "Half started", objective: "x", status: "authorized" }) }));
  await page.route("**/api/v1/missions/mission-0/cancel", (route) => {
    calls.push("cancel mission-0");
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "mission-0", inception_id: "inception-0", title: "Half started", objective: "x", status: "cancelled" }) });
  });

  await page.goto("/");
  await expect(page.getByRole("article", { name: "Trinity proposal: Legacy proposal" }).getByText("NOT VIABLE YET")).toBeVisible();
  const card = page.getByRole("article", { name: "Trinity proposal: Half started" });
  await card.getByRole("button", { name: "Cancel" }).click();

  await expect(card.getByText("Cancelled")).toBeVisible();
  await expect(card.getByText("TRINITY MISSION")).toBeVisible();
  expect(calls).toEqual(["cancel mission-0"]);
});
