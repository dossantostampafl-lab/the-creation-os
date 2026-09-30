export type VoiceTicket = { ticket: string };

export type VoiceSocket = {
  onclose: (() => void) | null;
  send: (payload: string) => void;
  close: () => void;
};

export type VoiceSessionTransportOptions = {
  apiBase: string;
  issueTicket: () => Promise<VoiceTicket>;
  socketFactory: (url: string) => VoiceSocket;
  conversationId?: string;
};

export function buildVoiceSessionUrl(
  apiBase: string,
  ticket: string,
  conversationId?: string,
): string {
  const base = new URL(apiBase);
  if (base.protocol !== "http:" && base.protocol !== "https:") {
    throw new Error("VOICE_SESSION_INVALID_API_BASE");
  }
  if (!ticket) throw new Error("VOICE_SESSION_TICKET_REQUIRED");

  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  const path = `${base.pathname.replace(/\/$/, "")}/voice/session`;
  const query = `ticket=${encodeURIComponent(ticket)}`
    + (conversationId ? `&conversation_id=${encodeURIComponent(conversationId)}` : "");
  return `${protocol}//${base.host}${path}?${query}`;
}

export class VoiceSessionTransport {
  private socket: VoiceSocket | null = null;

  constructor(private readonly options: VoiceSessionTransportOptions) {}

  async connect(): Promise<void> {
    const issued = await this.options.issueTicket();
    if (!issued.ticket) throw new Error("VOICE_SESSION_TICKET_REQUIRED");

    const socket = this.options.socketFactory(
      buildVoiceSessionUrl(
        this.options.apiBase,
        issued.ticket,
        this.options.conversationId,
      ),
    );
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null;
    };
    this.socket = socket;
  }

  async reconnect(): Promise<void> {
    this.socket?.close();
    this.socket = null;
    await this.connect();
  }

  send(payload: string): void {
    if (!this.socket) throw new Error("VOICE_SESSION_NOT_CONNECTED");
    this.socket.send(payload);
  }

  close(): void {
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }
}
