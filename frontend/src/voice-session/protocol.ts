export type GatewayState =
  | "ARMED"
  | "WAKE_DETECTED"
  | "LISTENING"
  | "THINKING"
  | "SPEAKING"
  | "RECOVERING"
  | "CLOSED";

export type SessionReadyEvent = {
  type: "session_ready";
  session_id: string;
  turn_id: number;
  state: GatewayState;
};

export type SessionStateEvent = {
  type: "state";
  session_id: string;
  turn_id: number;
  state: GatewayState;
};

export type VoiceServerEvent = SessionReadyEvent | SessionStateEvent;

export type BargeInEvent = {
  type: "barge_in";
  session_id: string;
  turn_id: number;
};
