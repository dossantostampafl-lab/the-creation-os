import { useEffect, useRef, useState } from "react";

import { API_BASE, issueVoiceSessionTicket, preloadVoiceAcknowledgement } from "../api";
import { bytesToBase64, MicrophonePcmCapture } from "./audio-capture";
import { Pcm16AudioSink, StreamingAudioPlayer } from "./player";
import type { VoiceServerEvent } from "./protocol";
import { parseVoiceServerEvent } from "./protocol";
import { VoiceSessionModel } from "./session";
import { buildVoiceSessionUrl } from "./transport";
import { VoiceActivityDetector } from "./vad";

export type RealtimeVoiceStatus =
  | "disabled"
  | "connecting"
  | "ready"
  | "listening"
  | "committing"
  | "thinking"
  | "speaking"
  | "reconnecting"
  | "error";

export type VoiceReply = {
  sessionId: string;
  turnId: number;
  text: string;
  provider: string | null;
};

export type UseDeusVoiceSessionOptions = {
  enabled: boolean;
  conversationId: string | null;
  onTranscript?: (text: string, turnId: number, sessionId: string) => void;
  onTextDelta?: (text: string, turnId: number, provider: string, sessionId: string) => void;
  onReply?: (reply: VoiceReply) => void;
  onWake?: () => void;
};

export type DeusVoiceSession = {
  status: RealtimeVoiceStatus;
  error: string | null;
  provider: string | null;
  fallbackReason: string | null;
  latencyMs: Record<string, number>;
};

function decodeBase64(encoded: string): Uint8Array {
  const binary = atob(encoded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function statusFromEvent(event: VoiceServerEvent): RealtimeVoiceStatus | null {
  if (event.type === "error") return "error";
  if (event.type === "transcript_commit") return "committing";
  if (event.type !== "session_ready" && event.type !== "state" && event.type !== "barge_in") return null;
  const state = event.state;
  switch (state) {
    case "DISCONNECTED":
    case "CONNECTING":
      return "connecting";
    case "ARMED":
      return "ready";
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
      return "disabled";
  }
}

export function useDeusVoiceSession(options: UseDeusVoiceSessionOptions): DeusVoiceSession {
  const { enabled, conversationId } = options;
  const callbacks = useRef(options);
  callbacks.current = options;
  const [status, setStatus] = useState<RealtimeVoiceStatus>(enabled ? "connecting" : "disabled");
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!enabled || !conversationId) {
      setStatus(enabled ? "connecting" : "disabled");
      return;
    }

    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let reconnectAttempt = 0;
    let bargeOpen = false;
    let vadWasSpeaking = false;
    let replyTurn = 0;
    let replyText = "";
    let replyProvider: string | null = null;
    let acknowledgementAudio: Uint8Array | null = null;
    let acknowledgementGeneration = 0;
    let completionGeneration = 0;
    const acknowledgementPromise = preloadVoiceAcknowledgement()
      .then((audio) => {
        acknowledgementAudio = audio;
        return audio;
      })
      .catch(() => null);

    const model = new VoiceSessionModel();
    const capture = new MicrophonePcmCapture();
    const vad = new VoiceActivityDetector({ threshold: 0.085, releaseFrames: 4 });
    const sink = new Pcm16AudioSink(24_000);
    const player = new StreamingAudioPlayer(sink);

    const send = (payload: object) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(payload));
      return true;
    };

    const sendAudio = (pcm16k: Uint8Array) => {
      if (!model.sessionId || !pcm16k.byteLength) return;
      send({
        type: "audio",
        session_id: model.sessionId,
        turn_id: model.turnId,
        audio_base64: bytesToBase64(pcm16k),
        commit: false,
        utterance_id: crypto.randomUUID(),
      });
    };

    const handleFrame = ({ float32, pcm16k }: { float32: Float32Array; pcm16k: Uint8Array }) => {
      const localSpeech = vad.update(float32);
      const beganSpeaking = localSpeech && !vadWasSpeaking;
      vadWasSpeaking = localSpeech;

      if (model.state === "speaking") {
        if (!bargeOpen && beganSpeaking) {
          const event = model.bargeIn();
          if (event && send(event)) {
            completionGeneration += 1;
            bargeOpen = true;
            player.cancel(event.turn_id);
            setStatus("listening");
          }
        }
        if (!bargeOpen) return;
      } else if (model.state === "thinking" || model.state === "committing") {
        return;
      }

      sendAudio(pcm16k);
    };

    const ensureCapture = async () => {
      try {
        await capture.start(handleFrame);
      } catch (failure) {
        if (disposed) return;
        setError(failure instanceof Error ? failure.message : "MICROPHONE_UNAVAILABLE");
        setStatus("error");
      }
    };

    const finishReply = (turnId: number) => {
      if (!replyText || replyTurn !== turnId) return;
      callbacks.current.onReply?.({ sessionId: model.sessionId ?? "", turnId, text: replyText, provider: replyProvider });
      replyText = "";
      replyProvider = null;
      replyTurn = 0;
    };

    const handleEvent = (event: VoiceServerEvent) => {
      if (event.type === "state" && event.state === "LISTENING"
        && model.state === "speaking" && event.session_id === model.sessionId
        && event.turn_id === model.turnId) {
        const generation = ++completionGeneration;
        void sink.whenDrained().then(() => {
          if (disposed || generation !== completionGeneration
            || model.sessionId !== event.session_id || model.turnId !== event.turn_id) return;
          if (!model.onServerEvent(event)) return;
          setStatus("listening");
          player.finish(event.turn_id);
          bargeOpen = false;
          vad.reset();
          vadWasSpeaking = false;
          finishReply(event.turn_id);
        });
        return;
      }
      if (!model.onServerEvent(event)) return;
      const nextStatus = statusFromEvent(event);
      if (nextStatus) setStatus(nextStatus);

      if (event.type === "session_ready") {
        replyTurn = 0;
        replyText = "";
        replyProvider = null;
        reconnectAttempt = 0;
        bargeOpen = false;
        setError(null);
        void ensureCapture();
        return;
      }
      if (event.type === "wake_detected") {
        callbacks.current.onWake?.();
        if (!event.acknowledge) return;
        const generation = ++acknowledgementGeneration;
        const play = (audio: Uint8Array | null) => {
          if (
            !audio
            || disposed
            || generation !== acknowledgementGeneration
          ) return;
          player.startTurn(event.turn_id);
          void sink.resume().catch(() => undefined);
          player.push(event.turn_id, audio);
        };
        if (acknowledgementAudio) play(acknowledgementAudio);
        else void acknowledgementPromise.then(play);
        return;
      }
      if (event.type === "transcript_commit") {
        completionGeneration += 1;
        acknowledgementGeneration += 1;
        player.stop();
        replyTurn = event.turn_id;
        replyText = "";
        replyProvider = null;
        callbacks.current.onTranscript?.(event.text, event.turn_id, event.session_id);
        return;
      }
      if (event.type === "text_delta") {
        if (replyTurn !== event.turn_id) {
          replyTurn = event.turn_id;
          replyText = "";
        }
        replyText += event.text;
        replyProvider = event.provider;
        setProvider(event.provider);
        callbacks.current.onTextDelta?.(event.text, event.turn_id, event.provider, event.session_id);
        return;
      }
      if (event.type === "audio_chunk") {
        setStatus("speaking");
        player.startTurn(event.turn_id);
        void sink.resume().catch(() => undefined);
        player.push(event.turn_id, decodeBase64(event.audio_base64));
        return;
      }
      if (event.type === "barge_in" && event.cancelled) {
        completionGeneration += 1;
        player.cancel(event.turn_id);
        bargeOpen = true;
        return;
      }
      if (event.type === "state" && event.state === "LISTENING") {
        player.finish(event.turn_id);
        bargeOpen = false;
        vad.reset();
        vadWasSpeaking = false;
        finishReply(event.turn_id);
        return;
      }
      if (event.type === "telemetry") {
        setProvider(event.provider_selected ?? replyProvider);
        setFallbackReason(event.fallback_reason ?? null);
        setLatencyMs(event.latency_ms ?? {});
        return;
      }
      if (event.type === "error") {
        setError(event.code);
      }
    };

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer !== null) return;
      completionGeneration += 1;
      acknowledgementGeneration += 1;
      player.stop();
      model.onSocketClosed();
      setStatus("reconnecting");
      const delay = Math.min(3000, 300 * 2 ** reconnectAttempt);
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, delay);
    };

    const connect = async () => {
      if (disposed) return;
      setStatus(reconnectAttempt ? "reconnecting" : "connecting");
      try {
        const { ticket } = await issueVoiceSessionTicket();
        if (disposed) return;
        const next = new WebSocket(buildVoiceSessionUrl(API_BASE, ticket, conversationId));
        socket = next;
        next.onmessage = (message) => {
          if (disposed || socket !== next) return;
          try {
            handleEvent(parseVoiceServerEvent(String(message.data)));
          } catch {
            setError("VOICE_SESSION_INVALID_SERVER_EVENT");
            setStatus("error");
          }
        };
        next.onerror = () => {
          if (!disposed) setError("VOICE_SESSION_CONNECTION_ERROR");
        };
        next.onclose = () => {
          if (socket === next) socket = null;
          if (!disposed) scheduleReconnect();
        };
      } catch (failure) {
        if (disposed) return;
        setError(failure instanceof Error ? failure.message : "VOICE_SESSION_CONNECTION_ERROR");
        scheduleReconnect();
      }
    };

    const resumeAudio = () => {
      void capture.resume().catch(() => undefined);
      void sink.resume().catch(() => undefined);
    };
    document.addEventListener("pointerdown", resumeAudio);
    document.addEventListener("keydown", resumeAudio);
    void connect();

    return () => {
      disposed = true;
      acknowledgementGeneration += 1;
      player.stop();
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      document.removeEventListener("pointerdown", resumeAudio);
      document.removeEventListener("keydown", resumeAudio);
      const current = socket;
      socket = null;
      if (current && current.readyState === WebSocket.OPEN && model.sessionId) {
        current.send(JSON.stringify({
          type: "stop",
          session_id: model.sessionId,
          turn_id: model.turnId,
        }));
      }
      current?.close();
      void capture.stop();
      void sink.close();
    };
  }, [enabled, conversationId]);

  return { status, error, provider, fallbackReason, latencyMs };
}
