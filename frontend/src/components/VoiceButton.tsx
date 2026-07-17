import { Mic, Square, Volume2 } from "lucide-react";
import type { VoiceConversationState } from "../voice";

type VoiceButtonProps = {
  state: VoiceConversationState;
  supported: boolean;
  disabled: boolean;
  onListen: () => void;
  onStopListening: () => void;
  onStopSpeaking: () => void;
};

export function VoiceButton({ state, supported, disabled, onListen, onStopListening, onStopSpeaking }: VoiceButtonProps) {
  if (state === "listening") {
    return (
      <button className="voice-orb listening" type="button" onClick={onStopListening} aria-label="Parar escuta">
        <Square size={18} />
      </button>
    );
  }

  if (state === "speaking") {
    return (
      <button className="voice-orb speaking" type="button" onClick={onStopSpeaking} aria-label="Interromper voz de GOD">
        <Volume2 size={19} />
      </button>
    );
  }

  return (
    <button
      className="voice-orb"
      type="button"
      disabled={disabled || !supported}
      onClick={onListen}
      aria-label={supported ? "Iniciar conversa por voz" : "Reconhecimento de voz indisponivel"}
      title={supported ? "Iniciar conversa por voz" : "Reconhecimento de voz indisponivel"}
    >
      <Mic size={19} />
    </button>
  );
}
