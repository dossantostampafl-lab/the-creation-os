export type GatewayState =
  | "DISCONNECTED"
  | "CONNECTING"
  | "ARMED"
  | "WAKE_DETECTED"
  | "LISTENING"
  | "COMMITTING"
  | "THINKING"
  | "SPEAKING"
  | "RECOVERING"
  | "CLOSED";

export type SessionReadyEvent = {
  type: "session_ready";
  session_id: string;
  turn_id: number;
  state: GatewayState;
  creator_id?: string;
};

export type SessionStateEvent = {
  type: "state";
  session_id: string;
  turn_id: number;
  state: GatewayState;
};

export type WakeDetectedEvent = {
  type: "wake_detected";
  session_id: string;
  turn_id: number;
  acknowledge: boolean;
};

export type TranscriptCommitEvent = {
  type: "transcript_commit";
  session_id: string;
  turn_id: number;
  text: string;
};

export type TextDeltaEvent = {
  type: "text_delta";
  session_id: string;
  turn_id: number;
  provider: string;
  text: string;
};

export type AudioChunkEvent = {
  type: "audio_chunk";
  session_id: string;
  turn_id: number;
  audio_base64: string;
};

export type BargeInServerEvent = {
  type: "barge_in";
  session_id: string;
  turn_id: number;
  cancelled: boolean;
  state: GatewayState;
};

export type TelemetryEvent = {
  type: "telemetry";
  session_id: string;
  turn_id: number;
  provider_selected?: string | null;
  fallback_reason?: string | null;
  latency_ms?: Record<string, number>;
};

export type ErrorEvent = {
  type: "error";
  code: string;
  message: string;
  nonretryable?: boolean;
};

export type StaleSessionEvent = {
  type: "stale_session";
  session_id: string;
  turn_id: number;
};

export type VoiceServerEvent =
  | SessionReadyEvent
  | SessionStateEvent
  | WakeDetectedEvent
  | TranscriptCommitEvent
  | TextDeltaEvent
  | AudioChunkEvent
  | BargeInServerEvent
  | TelemetryEvent
  | ErrorEvent
  | StaleSessionEvent;

export type BargeInEvent = {
  type: "barge_in";
  session_id: string;
  turn_id: number;
};

export type AudioClientEvent = {
  type: "audio";
  session_id: string;
  turn_id: number;
  audio_base64: string;
  commit: boolean;
  utterance_id: string;
};

export type StopEvent = {
  type: "stop";
  session_id: string;
  turn_id: number;
};

export type VoiceClientEvent = BargeInEvent | AudioClientEvent | StopEvent;

export function parseVoiceServerEvent(raw: string): VoiceServerEvent {
  const value = JSON.parse(raw) as unknown;
  if (!value || typeof value !== "object" || !("type" in value)) {
    throw new Error("VOICE_SESSION_INVALID_SERVER_EVENT");
  }
  return value as VoiceServerEvent;
}
