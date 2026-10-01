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
  private cancelledTurnId: number | null = null;

  onServerEvent(event: VoiceServerEvent): boolean {
    if (event.type === "error") {
      this.error = event.code;
      this.state = "error";
      return true;
    }

    if (event.type === "stale_session") return false;

    if (event.type === "session_ready") {
      this.sessionId = event.session_id;
      this.turnId = event.turn_id;
      this.state = clientState(event.state);
      this.error = null;
      this.cancelledTurnId = null;
      return true;
    }

    if (!("session_id" in event) || !("turn_id" in event)) return false;
    if (this.state === "reconnecting" || this.state === "closed") return false;
    if (!this.sessionId || event.session_id !== this.sessionId) return false;
    if (event.turn_id < this.turnId) return false;
    if (event.turn_id === this.cancelledTurnId && (event.type === "text_delta" || event.type === "audio_chunk")) return false;

    this.turnId = event.turn_id;
    if (event.type === "audio_chunk") this.state = "speaking";
    if (event.type === "state") this.state = clientState(event.state);
    if (event.type === "barge_in" && event.cancelled) {
      this.cancelledTurnId = event.turn_id;
      this.state = clientState(event.state);
    }
    return true;
  }

  onSocketClosed(): void {
    if (this.state !== "closed") this.state = "reconnecting";
  }

  bargeIn(): BargeInEvent | null {
    if (this.state !== "speaking" || !this.sessionId) return null;
    this.cancelledTurnId = this.turnId;
    this.state = "listening";
    return {
      type: "barge_in",
      session_id: this.sessionId,
      turn_id: this.turnId,
    };
  }
}
