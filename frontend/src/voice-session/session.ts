import type { BargeInEvent, GatewayState, VoiceServerEvent } from "./protocol";

export type VoiceClientState =
  | "connecting"
  | "armed"
  | "listening"
  | "committing"
  | "thinking"
  | "speaking"
  | "reconnecting"
  | "closed"
  | "error";

function clientState(state: GatewayState): VoiceClientState {
  switch (state) {
    case "DISCONNECTED":
    case "CONNECTING":
      return "connecting";
    case "ARMED":
      return "armed";
    case "WAKE_DETECTED":
    case "LISTENING":
      return "listening";
    case "COMMITTING":
      return "committing";
    case "THINKING":
      return "thinking";
    case "SPEAKING":
      return "speaking";
    case "RECOVERING":
      return "reconnecting";
    case "CLOSED":
      return "closed";
  }
}

export class VoiceSessionModel {
  sessionId: string | null = null;
  turnId = 0;
  state: VoiceClientState = "connecting";
  error: string | null = null;

  onServerEvent(event: VoiceServerEvent): void {
    if (event.type === "error") {
      this.error = event.code;
      this.state = "error";
      return;
    }

    if (event.type === "stale_session") return;

    if (event.type === "session_ready") {
      this.sessionId = event.session_id;
      this.turnId = event.turn_id;
      this.state = clientState(event.state);
      this.error = null;
      return;
    }

    if (!("session_id" in event) || !("turn_id" in event)) return;
    if (this.state === "reconnecting") return;
    if (!this.sessionId || event.session_id !== this.sessionId) return;
    if (event.turn_id < this.turnId) return;

    this.turnId = event.turn_id;
    if (event.type === "state") this.state = clientState(event.state);
    if (event.type === "barge_in" && event.cancelled) {
      this.state = clientState(event.state);
    }
  }

  onSocketClosed(): void {
    if (this.state !== "closed") this.state = "reconnecting";
  }

  bargeIn(): BargeInEvent | null {
    if (this.state !== "speaking" || !this.sessionId) return null;
    return {
      type: "barge_in",
      session_id: this.sessionId,
      turn_id: this.turnId,
    };
  }
}
