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

test("renders the Living Operations Terminal from projection-backed state", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("creation_access_token", "e2e-token"));
  await page.route("**/api/v1/system/state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projections) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(chronicle) }));
  await page.route("**/api/v1/system/events?after=41", (route) => route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: "id: 42\nevent: chronicle\ndata: {\"event_id\":\"event-42\",\"position\":42,\"correlation_id\":\"corr\",\"causation_id\":null,\"actor_role\":\"agent\",\"event_type\":\"task_progressed\",\"aggregate_type\":\"task\",\"aggregate_id\":\"task-1\",\"payload\":{},\"created_at\":\"2026-09-08T15:00:01Z\"}\n\n",
  }));

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Living Cognitive Operating System" })).toBeVisible();
  await expect(page.getByText("DEUS", { exact: true })).toBeVisible();
  await expect(page.getByText("SOPHIA", { exact: true })).toBeVisible();
  await expect(page.getByText("ROCKMAM", { exact: true })).toBeVisible();
  await expect(page.getByText("Manifest Gate D", { exact: true })).toBeVisible();
  await expect(page.getByText("Engineering", { exact: true })).toBeVisible();
  await expect(page.getByText("Builder", { exact: true })).toBeVisible();
  await expect(page.getByText("mission_distributed", { exact: true })).toBeVisible();
  await expect(page.getByText("kernel_health", { exact: true })).toBeVisible();
  await expect(page.getByText("task_progressed", { exact: true })).toBeVisible();
  await expect(page.locator(".top-status .status")).toHaveText("LIVE");
});

test("fails closed when Creator authentication is absent", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".top-status .status")).toHaveText("AUTH_REQUIRED");
  await expect(page.getByText(/Authentication required/)).toBeVisible();
});
