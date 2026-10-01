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
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ configured: true, configured_provider: "freellmapi", providers: [{ provider: "freellmapi", available: true, detail: null, models: [] }] }) }));
  await page.route("**/api/v1/system/events?after=1", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/voice/session/ticket", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ ticket: "voice-ticket" }) }));
}

test("an expired access token is refreshed once and typed DEUS chat keeps working", async ({ page }) => {
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

  await page.goto("/");
  await expect(page.getByText("LIVE", { exact: true })).toBeVisible();
  await page.getByLabel("Message DEUS").fill("Deus, está me ouvindo?");
  await page.getByRole("button", { name: "Send to DEUS" }).click();
  await expect(page.getByText("Estou aqui.", { exact: true })).toBeVisible();
  expect(refreshes).toBe(1);
  await expect(page.evaluate(() => sessionStorage.getItem("creation_refresh_token"))).resolves.toBe("refresh-2");
});
