import { expect, test } from "@playwright/test";

const state = {
  projection: "system",
  position: 41,
  generated_at: "2026-09-08T15:00:00Z",
  missions: [
    { id: "mission-1", title: "Manifest Alpha", objective: "Validate full mission", status: "executing", started_at: null, completed_at: null },
  ],
  tasks: [
    { id: "task-00000001", mission_id: "mission-1", step_id: "step-1", universe_id: "universe-1", agent_id: "agent-1", status: "RUNNING", attempt_count: 1, max_attempts: 3 },
  ],
  universes: [{ id: "universe-1", code: "engineering", name: "Engineering", active: true }],
  agents: [{ id: "agent-1", code: "architect", name: "Architect", universe_id: "universe-1", active: true }],
  memory: { conversation: 2, mission: 3, universe: 1, conscious: 4, total: 10 },
  pulse: {},
  counts: { missions: 1, running_missions: 1, tasks: 1, ready_tasks: 0, running_tasks: 1, failed_tasks: 0, active_universes: 1, active_agents: 1 },
};

const projections = {
  chronicle_head: 41,
  projections: [
    { name: "system", position: 41, lag: 0, status: "CURRENT", updated_at: "2026-09-08T15:00:00Z" },
    { name: "missions", position: 41, lag: 0, status: "CURRENT", updated_at: "2026-09-08T15:00:00Z" },
    { name: "tasks", position: 41, lag: 0, status: "CURRENT", updated_at: "2026-09-08T15:00:00Z" },
    { name: "agents", position: 41, lag: 0, status: "CURRENT", updated_at: "2026-09-08T15:00:00Z" },
    { name: "memory", position: 41, lag: 0, status: "CURRENT", updated_at: "2026-09-08T15:00:00Z" },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem("creation-session", JSON.stringify({ accessToken: "test-token", refreshToken: "refresh", expiresIn: 15 }));
  });
  await page.route("**/api/v1/system/state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(projections) }));
  await page.route("**/api/v1/system/events?after=41", (route) => route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    body: ": keepalive\n\n",
  }));
});

test("renders the approved high-density operational structure from real projection payloads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("LIVING CORE VISUALIZATION")).toBeVisible();
  await expect(page.getByText("SYSTEM HIERARCHY")).toBeVisible();
  await expect(page.getByText("MEMORY LAYERS")).toBeVisible();
  await expect(page.getByText("TASK DAG")).toBeVisible();
  await expect(page.getByText("SYSTEM EVENTS")).toBeVisible();
  await expect(page.getByText("Manifest Alpha")).toBeVisible();
  await expect(page.getByText("Engineering")).toBeVisible();
  await expect(page.getByText("Architect")).toBeVisible();
  await expect(page.getByText("41", { exact: true }).first()).toBeVisible();
});

test("does not invent rows when backend projections are empty", async ({ page }) => {
  await page.route("**/api/v1/system/state", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ ...state, missions: [], tasks: [], universes: [], agents: [], memory: { conversation: 0, mission: 0, universe: 0, conscious: 0, total: 0 }, counts: { missions: 0, running_missions: 0, tasks: 0, ready_tasks: 0, running_tasks: 0, failed_tasks: 0, active_universes: 0, active_agents: 0 } }),
  }));
  await page.goto("/");
  await expect(page.getByText("Nenhuma missão persistida.")).toBeVisible();
  await expect(page.getByText("Nenhuma task persistida.")).toBeVisible();
  await expect(page.getByText("Manifest Alpha")).toHaveCount(0);
});
