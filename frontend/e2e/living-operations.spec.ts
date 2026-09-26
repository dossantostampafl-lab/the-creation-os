import { expect, test } from "@playwright/test";

const state = {
  projection: "system",
  position: 41,
  generated_at: "2026-09-08T15:00:00Z",
  missions: [
    {
      id: "mission-1",
      title: "Manifest Gate D",
      objective: "Render live operational state",
      status: "executing",
      started_at: "2026-09-08T14:55:00Z",
      completed_at: null,
    },
  ],
  tasks: [
    {
      id: "task-1",
      mission_id: "mission-1",
      step_id: "step-1",
      universe_id: "universe-1",
      agent_id: "agent-1",
      status: "RUNNING",
      attempt_count: 1,
      max_attempts: 3,
    },
  ],
  universes: [{ id: "universe-1", code: "engineering", name: "Engineering", active: true }],
  agents: [{ id: "agent-1", code: "builder", name: "Builder", universe_id: "universe-1", active: true }],
  memory: { conversation: 2, mission: 3, universe: 4, conscious: 5, total: 14 },
  pulse: { kernel_health: { value: "healthy", observed_at: "2026-09-08T15:00:00Z" } },
  counts: {
    missions: 1,
    running_missions: 1,
    tasks: 1,
    ready_tasks: 0,
    running_tasks: 1,
    failed_tasks: 0,
    active_universes: 1,
    active_agents: 1,
  },
};

const projections = {
  chronicle_head: 41,
  projections: [
    { name: "system", position: 41, lag: 0, status: "CURRENT", updated_at: "2026-09-08T15:00:00Z" },
    { name: "missions", position: 41, lag: 0, status: "CURRENT", updated_at: "2026-09-08T15:00:00Z" },
  ],
};

const chronicle = [
  {
    id: "chronicle-41",
    event_id: "event-41",
    correlation_id: "corr-41",
    causation_id: null,
    actor_type: "creator",
    actor_id: "creator-1",
    event_type: "mission_distributed",
    aggregate_type: "mission",
    aggregate_id: "mission-1",
    payload_json: {},
    payload_hash: "hash",
    previous_hash: null,
    created_at: "2026-09-08T15:00:00Z",
  },
];

const inference = {
  configured: true,
  configured_provider: "freellmapi",
  providers: [
    {
      provider: "freellmapi",
      available: true,
      detail: null,
      models: [
        {
          model: "auto:default",
          is_default: true,
          capabilities: ["streaming", "text"],
          cost_tier: "UNKNOWN",
        },
      ],
    },
  ],
};

async function mockOperationalApi(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/system/state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projections) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(chronicle) }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(inference) }));
  await page.route("**/api/v1/system/events?after=41", (route) => route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: "id: 42\nevent: chronicle\ndata: {\"event_id\":\"event-42\",\"position\":42,\"correlation_id\":\"corr\",\"causation_id\":null,\"actor_role\":\"agent\",\"event_type\":\"task_progressed\",\"aggregate_type\":\"task\",\"aggregate_id\":\"task-1\",\"payload\":{},\"created_at\":\"2026-09-08T15:00:01Z\"}\n\n",
  }));
}

test("renders the Living Operations Terminal from projection-backed state", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await mockOperationalApi(page);

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Living Cognitive Operating System" })).toBeVisible();
  await expect(page.locator(".deus")).toHaveText("DEUS");
  await expect(page.locator(".orbit-a span")).toHaveText("SOPHIA");
  await expect(page.locator(".orbit-b span")).toHaveText("ROCKMAM");
  await expect(page.getByRole("heading", { name: "Manifest Gate D" })).toBeVisible();
  await expect(page.locator(".universe-label")).toHaveText("Engineering");
  await expect(page.locator(".top-status .status")).toHaveText("LIVE");
  await expect(page.getByRole("textbox", { name: "Message DEUS" })).toBeVisible();

  await expect(page.locator(".deus-presence")).toHaveAttribute("data-presence", "humanoid");
  await expect(page.getByText("DEUS · IDLE", { exact: true })).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Creator decisions" })).toBeHidden();
  const decisionsTrigger = page.getByRole("button", { name: "Creator decisions" });
  await expect(decisionsTrigger).toHaveAttribute("aria-expanded", "false");
  await decisionsTrigger.click();
  await expect(decisionsTrigger).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("complementary", { name: "Creator decisions" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Close decisions" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(decisionsTrigger).toBeFocused();

  const vitalsTrigger = page.getByRole("button", { name: "System vitals" });
  await vitalsTrigger.click();
  const vitals = page.getByRole("complementary", { name: "System vitals" });
  await expect(vitals.getByText("Engineering", { exact: true })).toBeVisible();
  await expect(vitals.getByText("Builder", { exact: true })).toBeVisible();
  await expect(vitals.getByText("mission_distributed", { exact: true })).toBeVisible();
  await expect(vitals.getByText("kernel_health", { exact: true })).toBeVisible();
  await expect(vitals.locator(".system-events .event-list").getByText("task_progressed", { exact: true })).toBeVisible();
  await expect(vitals.getByText("INFERENCE FABRIC", { exact: true })).toBeVisible();
  await expect(vitals.getByText("freellmapi", { exact: true })).toBeVisible();
  await expect(vitals.getByText("auto:default", { exact: true })).toBeVisible();
  await expect(vitals.getByText("streaming · text", { exact: true })).toBeVisible();
  await expect(vitals.getByText("UNKNOWN", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close system vitals" }).click();
  await expect(vitals).toBeHidden();
  await expect(vitalsTrigger).toBeFocused();
});

test("renders an explicit unconfigured inference state without fabricated providers", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await page.route("**/api/v1/system/state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projections) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(chronicle) }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ configured: false, configured_provider: "fake", providers: [] }) }));
  await page.route("**/api/v1/system/events?after=41", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));

  await page.goto("/");
  await page.getByRole("button", { name: "System vitals" }).click();

  await expect(page.getByText("INFERENCE FABRIC", { exact: true })).toBeVisible();
  await expect(page.getByText("UNCONFIGURED", { exact: true })).toBeVisible();
  await expect(page.getByText("fake", { exact: true })).toBeVisible();
});

test("presents a Creator login instead of requiring manual localStorage setup", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Creator Access" })).toBeVisible();
  await expect(page.getByLabel("Username")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
  const reveal = page.getByRole("button", { name: "Show password" });
  await reveal.click();
  await expect(page.getByLabel("Password")).toHaveAttribute("type", "text");
  await expect(page.getByRole("button", { name: "Hide password" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Enter The Creation" })).toBeVisible();
  await page.getByRole("button", { name: "Enter The Creation" }).click();
  await expect(page.getByText("Enter your username and password.")).toBeVisible();
  await expect(page.getByLabel("Username")).toBeFocused();
});

test("authenticates the Creator and hydrates the live dashboard", async ({ page }) => {
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ access_token: "e2e-token", refresh_token: "e2e-refresh", token_type: "bearer", expires_in: 15 }),
  }));
  await mockOperationalApi(page);

  await page.goto("/");
  await page.getByLabel("Username").fill("creator");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Enter The Creation" }).click();

  await expect(page.locator(".top-status .status")).toHaveText("LIVE");
  await expect(page.getByRole("heading", { name: "Manifest Gate D" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("creation_access_token"))).toBe("e2e-token");
});


test("keeps the authenticated terminal non-indexable", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.locator('meta[name="googlebot"]')).toHaveAttribute("content", /noindex/);
});

test("shows a skeleton while real API state is delayed", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await page.route("**/api/v1/**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 900));
    const url = route.request().url();
    if (url.includes("/system/state")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) });
    if (url.includes("/system/projections")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projections) });
    if (url.includes("/system/inference")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(inference) });
    if (url.includes("/chronicles")) return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(chronicle) });
    return route.fulfill({ status: 200, contentType: "text/event-stream", body: "" });
  });
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("Loading live system state");
  await expect(page.locator(".top-status .status")).toHaveText("LIVE", { timeout: 6000 });
});

test("recovers from an offline API with the explicit Retry action", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  let offline = true;
  await page.route("**/api/v1/system/state", (route) => {
    if (offline) return route.fulfill({ status: 503, body: "offline" });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) });
  });
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projections) }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(inference) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(chronicle) }));
  await page.route("**/api/v1/system/events?after=41", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Live state unavailable");
  offline = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.locator(".top-status .status")).toHaveText("LIVE", { timeout: 6000 });
});

test("does not introduce horizontal overflow on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await mockOperationalApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Living Cognitive Operating System" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBeTruthy();
});


test("executes the Creator Console send action and renders the DEUS response", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await mockOperationalApi(page);
  const conversation = { id: "conversation-1", creator_id: "creator-1", title: "Creator Session", status: "active", created_at: "2026-09-18T21:00:00Z", updated_at: "2026-09-18T21:00:00Z" };
  let messageReads = 0;
  await page.route("**/api/v1/conversations", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(conversation) }));
  await page.route("**/api/v1/conversations/conversation-1/deus", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ response: "Acknowledged" }) }));
  await page.route("**/api/v1/conversations/conversation-1/messages", (route) => {
    messageReads += 1;
    const body = messageReads > 0 ? [{ id:"message-1", conversation_id:"conversation-1", actor_id:"deus", role:"deus", content:"Acknowledged", route:"deus", metadata_json:{}, correlation_id:"corr", created_at:"2026-09-18T21:00:01Z" }] : [];
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/");
  await page.getByLabel("Message DEUS").fill("Status report");
  await page.getByRole("button", { name: "Send to DEUS" }).click();
  await expect(page.getByText("Acknowledged", { exact: true })).toBeVisible();
});

test("keeps a failed Creator login actionable and does not enter the dashboard", async ({ page }) => {
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({ status: 401, body: "unauthorized" }));
  await page.goto("/");
  await page.getByLabel("Username").fill("creator");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Enter The Creation" }).click();
  await expect(page.getByText("Invalid username or password.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Enter The Creation" })).toBeEnabled();
});
