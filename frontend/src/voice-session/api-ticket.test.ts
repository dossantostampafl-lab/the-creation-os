import { beforeEach, describe, expect, it, vi } from "vitest";

import { issueVoiceSessionTicket } from "../api";

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
