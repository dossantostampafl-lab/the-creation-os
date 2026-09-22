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

test("DEUS speaks its reply aloud and the voice can be muted", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("creation_access_token", "e2e-token");
    const spoken: string[] = [];
    (window as unknown as { __spoken: string[] }).__spoken = spoken;
    const synth = {
      speaking: false,
      getVoices: () => [],
      cancel: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      speak: (utterance: SpeechSynthesisUtterance) => {
        spoken.push(utterance.text);
        const fire = (name: "onstart" | "onboundary" | "onend", extra: object = {}) =>
          (utterance[name] as ((event: unknown) => void) | null)?.({ name: "word", ...extra });
        setTimeout(() => { fire("onstart"); fire("onboundary"); fire("onend"); }, 10);
      },
    };
    Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
  });
  await mockDashboard(page);
  await page.route("**/api/v1/conversations", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "conversation-1" }) }));
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => route.fulfill({ status: 201, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([
    { id: "m1", conversation_id: "conversation-1", actor_id: "creator-1", role: "creator", content: "Status?", route: "deus", metadata_json: {}, correlation_id: "c1", created_at: "2026-09-11T12:00:01Z" },
    { id: "m2", conversation_id: "conversation-1", actor_id: "deus", role: "deus", content: "**All** universes are breathing.", route: "deus", metadata_json: {}, correlation_id: "c1", created_at: "2026-09-11T12:00:02Z" },
  ]) }));

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Status?");
  await page.getByLabel("Message DEUS").press("Enter");

  await expect(page.getByText("**All** universes are breathing.", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as unknown as { __spoken: string[] }).__spoken)).toEqual(["All universes are breathing."]);

  await page.getByRole("button", { name: "Mute DEUS voice" }).click();
  await expect(page.getByRole("button", { name: "Unmute DEUS voice" })).toBeVisible();
});
