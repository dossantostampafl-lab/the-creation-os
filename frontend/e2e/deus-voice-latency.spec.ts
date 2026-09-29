import { expect, test } from "@playwright/test";

const state = {
  projection: "system",
  position: 1,
  generated_at: "2026-09-28T22:30:00Z",
  missions: [], tasks: [], universes: [], agents: [],
  memory: { conversation: 0, mission: 0, universe: 0, conscious: 0, total: 0 },
  pulse: {},
  counts: { missions: 0, running_missions: 0, tasks: 0, ready_tasks: 0, running_tasks: 0, failed_tasks: 0, active_universes: 0, active_agents: 0 },
  pagination: { page: 1, page_size: 25, has_next: false, totals: { missions: 0, tasks: 0, universes: 0, agents: 0 } },
};

async function mockDashboard(page: import("@playwright/test").Page) {
  await page.route(/\/api\/v1\/system\/state(?:\?.*)?$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }));
  await page.route("**/api/v1/system/projections", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ chronicle_head: 1, projections: [] }) }));
  await page.route("**/api/v1/chronicles?limit=40&offset=0", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/system/inference", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ configured: true, configured_provider: "stub", providers: [{ provider: "stub", available: true, detail: null, models: [] }] }) }));
  await page.route("**/api/v1/system/events?after=1", (route) => route.fulfill({ status: 200, contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/inceptions", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/conversations", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "conversation-voice" }) }));
  await page.route("**/api/v1/conversations/conversation-voice/messages", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
}

async function installVoiceFakes(page: import("@playwright/test").Page, wakeEnabled: boolean) {
  await page.addInitScript(({ wakeEnabled: wake }) => {
    localStorage.setItem("creation_access_token", "voice-test-token");
    localStorage.removeItem("creation_conversation_id");
    localStorage.setItem("creation_wake_word_v3", wake ? "on" : "off");

    type TestScope = Window & {
      __recognizer?: FakeRecognition;
      __say?: (text: string, confidence?: number) => boolean;
      __recorderStarted?: boolean;
      __audioPlaying?: boolean;
      __audioPauses?: number;
    };
    const scope = window as TestScope;
    scope.__audioPauses = 0;

    class FakeRecognition {
      running = false;
      lang = "";
      interimResults = false;
      continuous = false;
      maxAlternatives = 1;
      onresult: ((event: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      onerror: ((event: unknown) => void) | null = null;
      start() { this.running = true; scope.__recognizer = this; }
      stop() { this.running = false; this.onend?.(); }
      abort() { this.stop(); }
    }

    class FakeMediaRecorder {
      state = "inactive";
      mimeType = "audio/webm";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      constructor(_stream: unknown) {}
      start() {
        this.state = "recording";
        scope.__recorderStarted = true;
      }
      stop() {
        if (this.state === "inactive") return;
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob([new Uint8Array(1024)], { type: this.mimeType }) });
        this.onstop?.();
      }
    }

    Object.defineProperty(window, "SpeechRecognition", { configurable: true, value: FakeRecognition });
    Object.defineProperty(window, "webkitSpeechRecognition", { configurable: true, value: FakeRecognition });
    Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeMediaRecorder });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => undefined }] }) },
    });

    scope.__say = (text: string, confidence = 0.99) => {
      const recognition = scope.__recognizer;
      if (!recognition?.running) return false;
      const result = Object.assign([{ transcript: text, confidence }], { isFinal: true });
      recognition.onresult?.({ resultIndex: 0, results: [result] });
      return true;
    };

    class FakeAudio {
      onended: (() => void) | null = null;
      onerror: (() => void) | null = null;
      paused = true;
      constructor(_src?: string) {}
      play() {
        this.paused = false;
        scope.__audioPlaying = true;
        return Promise.resolve();
      }
      pause() {
        this.paused = true;
        scope.__audioPauses = (scope.__audioPauses ?? 0) + 1;
      }
    }
    Object.defineProperty(window, "Audio", { configurable: true, value: FakeAudio });
  }, { wakeEnabled });
}

async function routeVoiceTurn(page: import("@playwright/test").Page, serverText = "verifique o projeto") {
  let sttCalls = 0;
  const deusBodies: Array<{ content: string }> = [];
  await page.route("**/api/v1/voice/transcribe", (route) => {
    sttCalls += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ text: serverText, language_code: "por", language_probability: 1 }) });
  });
  await page.route("**/api/v1/conversations/conversation-voice/deus", (route) => {
    deusBodies.push(route.request().postDataJSON() as { content: string });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ message_id: `m${deusBodies.length}`, conversation_id: "conversation-voice", route: "deus", response: "Verificando.", inception: null, correlation_id: `c${deusBodies.length}` }) });
  });
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from("ID3-fake") }));
  return { sttCalls: () => sttCalls, deusBodies };
}

test("active voice turn uses server STT even when browser confidence is high", async ({ page }) => {
  await installVoiceFakes(page, false);
  await mockDashboard(page);
  const turn = await routeVoiceTurn(page);

  await page.goto("/");
  await page.getByRole("button", { name: "Talk to DEUS" }).click();
  await expect.poll(() => page.evaluate(() => Boolean((window as Window & { __recorderStarted?: boolean }).__recorderStarted))).toBe(true);
  await expect.poll(() => page.evaluate(() => (window as Window & { __say?: (text: string, confidence?: number) => boolean }).__say?.("texto errado do navegador", 0.99) ?? false)).toBe(true);

  await expect.poll(turn.sttCalls).toBe(1);
  await expect.poll(() => turn.deusBodies[0]?.content).toBe("verifique o projeto");
});

test("active voice turn uses server STT when Chromium reports zero confidence", async ({ page }) => {
  await installVoiceFakes(page, false);
  await mockDashboard(page);
  const turn = await routeVoiceTurn(page, "continue o projeto");

  await page.goto("/");
  await page.getByRole("button", { name: "Talk to DEUS" }).click();
  await expect.poll(() => page.evaluate(() => Boolean((window as Window & { __recorderStarted?: boolean }).__recorderStarted))).toBe(true);
  await expect.poll(() => page.evaluate(() => (window as Window & { __say?: (text: string, confidence?: number) => boolean }).__say?.("texto incompleto", 0) ?? false)).toBe(true);

  await expect.poll(turn.sttCalls).toBe(1);
  await expect.poll(() => turn.deusBodies[0]?.content).toBe("continue o projeto");
});

test("wake acknowledgement keeps ears open and immediate speech reaches DEUS once through server STT", async ({ page }) => {
  await installVoiceFakes(page, true);
  await mockDashboard(page);
  const turn = await routeVoiceTurn(page);

  await page.goto("/");
  await expect.poll(() => page.evaluate(() => (window as Window & { __say?: (text: string, confidence?: number) => boolean }).__say?.("Deus", 0.99) ?? false)).toBe(true);
  await expect(page.getByText("Em conversa — diga “tchau” para encerrar")).toBeVisible();
  await expect.poll(() => page.evaluate(() => Boolean((window as Window & { __recorderStarted?: boolean }).__recorderStarted))).toBe(true);
  await expect.poll(() => page.evaluate(() => Boolean((window as Window & { __audioPlaying?: boolean }).__audioPlaying))).toBe(true);

  await expect.poll(() => page.evaluate(() => (window as Window & { __say?: (text: string, confidence?: number) => boolean }).__say?.("texto errado do navegador", 0.99) ?? false)).toBe(true);

  await expect.poll(turn.sttCalls).toBe(1);
  await expect.poll(() => turn.deusBodies.length).toBe(1);
  expect(turn.deusBodies[0].content).toBe("verifique o projeto");
  await expect.poll(() => page.evaluate(() => (window as Window & { __audioPauses?: number }).__audioPauses ?? 0)).toBeGreaterThan(0);
});

test("Deus plus a command in the same utterance is submitted exactly once", async ({ page }) => {
  await installVoiceFakes(page, true);
  await mockDashboard(page);
  const deusBodies: Array<{ content: string }> = [];
  await page.route("**/api/v1/conversations/conversation-voice/deus", (route) => {
    deusBodies.push(route.request().postDataJSON() as { content: string });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ message_id: "m1", conversation_id: "conversation-voice", route: "deus", response: "Verificando.", inception: null, correlation_id: "c1" }) });
  });
  await page.route("**/api/v1/voice/synthesize", (route) => route.fulfill({ status: 200, contentType: "audio/mpeg", body: Buffer.from("ID3-fake") }));

  await page.goto("/");
  await expect.poll(() => page.evaluate(() => (window as Window & { __say?: (text: string, confidence?: number) => boolean }).__say?.("Deus, verifique o projeto", 0.99) ?? false)).toBe(true);

  await expect.poll(() => deusBodies.length).toBe(1);
  expect(deusBodies[0].content).toBe("verifique o projeto");
});