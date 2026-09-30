import { describe, expect, it } from "vitest";

import { buildVoiceSessionUrl, VoiceSessionTransport } from "./transport";

class FakeSocket {
  onclose: (() => void) | null = null;
  readonly sent: string[] = [];

  send(payload: string): void {
    this.sent.push(payload);
  }

  close(): void {
    this.onclose?.();
  }
}

describe("voice session transport", () => {
  it("builds wss/ws URLs with only the ephemeral ticket", () => {
    const secure = new URL(buildVoiceSessionUrl("https://deus.example/api/v1", "ticket value"));
    expect(secure.protocol).toBe("wss:");
    expect(secure.pathname).toBe("/api/v1/voice/session");
    expect(secure.searchParams.get("ticket")).toBe("ticket value");

    const local = new URL(buildVoiceSessionUrl("http://localhost:8000/api/v1", "ticket-2"));
    expect(local.protocol).toBe("ws:");
    expect(local.pathname).toBe("/api/v1/voice/session");
    expect(local.searchParams.get("ticket")).toBe("ticket-2");
  });

  it("uses a fresh ticket on reconnect and never places an access token in the socket URL", async () => {
    const tickets = ["ticket-1", "ticket-2"];
    const urls: string[] = [];
    const sockets: FakeSocket[] = [];

    const transport = new VoiceSessionTransport({
      apiBase: "https://deus.example/api/v1",
      issueTicket: async () => ({ ticket: tickets.shift() ?? "missing" }),
      socketFactory: (url) => {
        urls.push(url);
        const socket = new FakeSocket();
        sockets.push(socket);
        return socket;
      },
    });

    await transport.connect();
    sockets[0].close();
    await transport.reconnect();

    expect(urls).toEqual([
      "wss://deus.example/api/v1/voice/session?ticket=ticket-1",
      "wss://deus.example/api/v1/voice/session?ticket=ticket-2",
    ]);
    expect(urls.join(" ")).not.toContain("creation_access_token");
    expect(urls.join(" ")).not.toContain("Bearer");
  });
});
