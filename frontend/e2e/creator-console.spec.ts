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
  pagination: { page: 1, page_size: 25, has_next: false, totals: { missions: 0, tasks: 0, universes: 0, agents: 0 } },
};

async function mockDashboard(page: import("@playwright/test").Page) {
  await page.route(/\/api\/v1\/system\/state(?:\?.*)?$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ chronicle_head: 1, projections: [] }) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ configured: true, configured_provider: "freellmapi", providers: [{ provider: "freellmapi", available: true, detail: null, models: [{ model: "auto", is_default: true, capabilities: ["text", "streaming"], cost_tier: "UNKNOWN" }] }] }) }));
  await page.route("**/api/v1/system/events?after=1", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/voice/session/ticket", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ticket: "voice-ticket" }) }));
}

async function mockConversation(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/conversations", (route) => route.fulfill({
    status: 201,
    contentType: "application/json",
    body: JSON.stringify({
      id: "conversation-1",
      creator_id: "creator-1",
      title: "Creator Session",
      status: "active",
      created_at: "2026-09-11T12:00:00Z",
      updated_at: "2026-09-11T12:00:00Z",
    }),
  }));
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
}

test("Creator can type to DEUS while realtime voice remains buttonless", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await mockDashboard(page);
  await mockConversation(page);
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => route.fulfill({
    status: 201,
    contentType: "application/json",
    body: JSON.stringify({
      message_id: "m1",
      conversation_id: "conversation-1",
      route: "deus",
      response: "Sistema operacional.",
      inception: null,
      correlation_id: "c1",
    }),
  }));

  await page.goto("/");
  await expect(page.getByRole("region", { name: "Creator Console" })).toBeVisible();
  await page.getByLabel("Message DEUS").fill("Status?");
  await page.getByRole("button", { name: "Send to DEUS" }).click();

  await expect(page.getByText("Status?", { exact: true })).toBeVisible();
  await expect(page.getByText("Sistema operacional.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Talk to DEUS|wake word|microphone/i })).toHaveCount(0);
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

async function mockTrinity(
  page: import("@playwright/test").Page,
  calls: Calls,
  inception: typeof readyInception | typeof blockedInception = readyInception,
) {
  await mockConversation(page);
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => route.fulfill({
    status: 201,
    contentType: "application/json",
    body: JSON.stringify({
      message_id: "m1",
      conversation_id: "conversation-1",
      route: "deus",
      correlation_id: "c1",
      response: "ROCKMAM preparou a missão.",
      inception: { id: inception.id, title: inception.title, status: inception.status, verdict: inception.trinity_assessment.verdict.result },
    }),
  }));
  await page.route("**/api/v1/inceptions/inception-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(inception) }));
  await page.route("**/api/v1/missions/mission-1", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "mission-1", inception_id: "inception-1", title: "Landing page", objective: "Publish a landing page.", status: "validated" }) }));
  await page.route("**/api/v1/missions/mission-1/start", (route) => {
    calls.push("start mission-1");
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "mission-1", inception_id: "inception-1", title: "Landing page", objective: "Publish a landing page.", status: "executing" }) });
  });
  await page.route("**/api/v1/inceptions/inception-1/reject", (route) => {
    calls.push("reject");
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...inception, status: "rejected" }) });
  });
}

test("a viable governed Mission still requires Creator authorization", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await mockDashboard(page);
  const calls: Calls = [];
  await mockTrinity(page, calls);

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Build a landing page");
  await page.getByLabel("Message DEUS").press("Enter");

  const card = page.getByRole("article", { name: "Trinity proposal: Landing page" });
  await expect(card.getByText("MISSION READY")).toBeVisible();
  await card.getByRole("button", { name: "Authorize & start" }).click();
  await expect(card.getByText("Executing")).toBeVisible();
  expect(calls).toEqual(["start mission-1"]);
});

test("an unstaffed governed Mission can be dismissed but not started", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await mockDashboard(page);
  const calls: Calls = [];
  await mockTrinity(page, calls, blockedInception);

  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Build a landing page");
  await page.getByLabel("Message DEUS").press("Enter");

  const card = page.getByRole("article", { name: "Trinity proposal: Landing page" });
  await expect(card.getByText("NOT VIABLE YET")).toBeVisible();
  await expect(card.getByRole("button", { name: "Authorize & start" })).toHaveCount(0);
  await card.getByRole("button", { name: "Dismiss" }).click();
  await expect(card.getByText("Dismissed")).toBeVisible();
  expect(calls).toEqual(["reject"]);
});
