import { expect, test } from "@playwright/test";

test("publishes installable Creation metadata and icons", async ({ request }) => {
  const documentResponse = await request.get("/");
  expect(documentResponse.ok()).toBeTruthy();
  const document = await documentResponse.text();
  expect(document).toContain('rel="manifest" href="/manifest.webmanifest"');
  expect(document).toContain("viewport-fit=cover");
  expect(document).toContain('rel="apple-touch-icon" href="/icons/icon-192.png"');

  const manifestResponse = await request.get("/manifest.webmanifest");
  expect(manifestResponse.headers()["content-type"]).toContain("application/manifest+json");
  const manifest = await manifestResponse.json();
  expect(manifest).toMatchObject({
    name: "The Creation OS",
    short_name: "Creation OS",
    start_url: "/",
    display: "standalone",
    theme_color: "#020508",
    background_color: "#020508",
  });
  expect(manifest.icons).toEqual(expect.arrayContaining([
    expect.objectContaining({ src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" }),
    expect.objectContaining({ src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" }),
    expect.objectContaining({ src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" }),
  ]));

  for (const icon of ["/icons/icon-192.png", "/icons/icon-512.png", "/icons/maskable-512.png"]) {
    const response = await request.get(icon);
    expect(response.ok(), icon).toBeTruthy();
    expect(response.headers()["content-type"], icon).toContain("image/png");
    expect((await response.body()).byteLength, icon).toBeGreaterThan(1_024);
  }
});

test("publishes the service worker as JavaScript", async ({ request }) => {
  const response = await request.get("/sw.js");
  expect(response.ok()).toBeTruthy();
  expect(response.headers()["content-type"]).toContain("javascript");
  expect((await response.body()).byteLength).toBeGreaterThan(1_000);
});

test("reports offline and available-update states without stale-current copy", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: false });
    window.dispatchEvent(new Event("offline"));
  });
  const offline = page.getByRole("status").filter({ hasText: "Connection unavailable" });
  await expect(offline).toContainText("Live data is not current");

  await page.evaluate(() => {
    Object.defineProperty(navigator, "onLine", { configurable: true, value: true });
    window.dispatchEvent(new Event("online"));
    window.dispatchEvent(new CustomEvent("pwa:update-available", { detail: { waiting: { postMessage: () => undefined } } }));
  });
  const reload = page.getByRole("button", { name: "Reload now" });
  await expect(reload).toBeVisible();
  await reload.focus();
  await expect(reload).toBeFocused();
});
