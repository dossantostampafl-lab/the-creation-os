import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

const nginx = readFileSync(new URL("../nginx.conf", import.meta.url), "utf8");
const policy = nginx.match(/Content-Security-Policy "([^"]+)"/)?.[1];

test("microphone capture delivers audio under the deployed content security policy", async ({ page }) => {
  expect(policy).toBeTruthy();
  await page.route("**/voice-capture-probe", (route) => route.fulfill({
    status: 200,
    contentType: "text/html",
    headers: { "Content-Security-Policy": policy! },
    body: "<!doctype html><title>Voice capture probe</title>",
  }));
  await page.goto("/voice-capture-probe");
  const frames = await page.evaluate(async () => {
    // Import the real capture module; never replace AudioWorklet or its module loader.
    const path = "/src/voice-session/audio-capture.ts";
    const { MicrophonePcmCapture } = await import(/* @vite-ignore */ path);
    const capture = new MicrophonePcmCapture();
    try {
      return await new Promise<number>((resolve, reject) => {
        let count = 0;
        const timeout = setTimeout(() => reject(new Error("NO_MICROPHONE_FRAMES")), 5000);
        void capture.start((frame: { pcm16k: Uint8Array }) => {
          if (frame.pcm16k.byteLength && ++count >= 3) {
            clearTimeout(timeout);
            resolve(count);
          }
        }).catch((error: Error) => {
          clearTimeout(timeout);
          reject(error);
        });
      });
    } finally {
      await capture.stop();
    }
  });
  expect(frames).toBeGreaterThanOrEqual(3);
});
