import { beforeEach, describe, expect, it, vi } from "vitest";

import { issueVoiceSessionTicket, preloadVoiceAcknowledgement } from "../api";

describe("issueVoiceSessionTicket", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (key: string) => key === "creation_access_token" ? "access-token-1" : null,
        removeItem: () => undefined,
      },
      sessionStorage: {
        getItem: () => null,
        removeItem: () => undefined,
      },
      setTimeout,
    });
  });

  it("authenticates over HTTP while keeping the access token out of the URL", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(
      JSON.stringify({ ticket: "ticket-1" }),
      {
        status: 201,
        headers: { "Content-Type": "application/json" },
      },
    ));
    vi.stubGlobal("fetch", fetchMock);

    await expect(issueVoiceSessionTicket()).resolves.toEqual({ ticket: "ticket-1" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/voice/session/ticket");
    expect(String(url)).not.toContain("access-token-1");
    expect(init?.headers).toMatchObject({
      Authorization: "Bearer access-token-1",
    });
  });
});


  it("preloads the fixed ElevenLabs wake acknowledgement over authenticated HTTP", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(
      new Uint8Array([1, 2, 3]),
      {
        status: 200,
        headers: {
          "Content-Type": "application/octet-stream",
          "X-DEUS-Audio-Format": "pcm_s16le",
          "X-DEUS-Audio-Sample-Rate": "24000",
        },
      },
    ));
    vi.stubGlobal("fetch", fetchMock);

    const audio = await preloadVoiceAcknowledgement();

    expect(Array.from(audio)).toEqual([1, 2, 3]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/voice/session/acknowledgement");
    expect(init?.headers).toMatchObject({
      Authorization: "Bearer access-token-1",
    });
  });
