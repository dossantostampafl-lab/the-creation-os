import type { BargeInEvent, GatewayState, VoiceServerEvent } from "./protocol";

export type VoiceClientState =
  | "connecting"
  | "armed"
  | "listening"
  | "thinking"
  | "speaking"
  | "reconnecting"
  | "closed";

function clientState(state: GatewayState): VoiceClientState {
  switch (state) {
    case "ARMED":
      return "armed";
    case "WAKE_DETECTED":
    case "LISTENING":
      return "listening";
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

  onServerEvent(event: VoiceServerEvent): void {
    if (event.type === "session_ready") {
      this.sessionId = event.session_id;
      this.turnId = event.turn_id;
      this.state = clientState(event.state);
      return;
    }

    if (this.state === "reconnecting") return;
    if (!this.sessionId || event.session_id !== this.sessionId) return;
    if (event.turn_id < this.turnId) return;

    this.turnId = event.turn_id;
    this.state = clientState(event.state);
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
