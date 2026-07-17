import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, X } from "lucide-react";
import { ApiError, api } from "../api";
import type { ChatItem, Mission, Opportunity } from "../types";
import { buildContextualVoiceMessage, createBrowserSpeechRecognizer, type VoiceConversationState } from "../voice";
import { VoiceButton } from "./VoiceButton";

type VoiceConversationProps = {
  authenticated: boolean;
  busy: boolean;
  token: string | null;
  chat: ChatItem[];
  missions: Mission[];
  opportunities: Opportunity[];
  onSendToGod: (text: string) => Promise<string>;
};

export function VoiceConversation({ authenticated, busy, token, chat, missions, opportunities, onSendToGod }: VoiceConversationProps) {
  const [state, setState] = useState<VoiceConversationState>("idle");
  const [transcript, setTranscript] = useState("");
  const [textInput, setTextInput] = useState("");
  const [godReply, setGodReply] = useState("");
  const [error, setError] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  const lastGodReply = useMemo(() => [...chat].reverse().find((item) => item.role === "god")?.text ?? null, [chat]);
  const context = useMemo(
    () => ({
      currentSubject: chat.at(-1)?.text.slice(0, 120) ?? null,
      missionTitle: missions[0]?.title ?? null,
      opportunityTitle: opportunities[0]?.title ?? null,
      pendingDecision: missions[0] ? "mission_authorization" : opportunities[0] ? "opportunity_review" : null,
      lastGodReply,
    }),
    [chat, lastGodReply, missions, opportunities],
  );

  const recognizer = useMemo(
    () =>
      createBrowserSpeechRecognizer({
        onStart: () => {
          setError(null);
          setState("listening");
        },
        onStop: () => setState((current) => (current === "listening" ? "idle" : current)),
        onTranscript: (text) => {
          setTranscript(text);
          void submitVoice(text);
        },
        onError: (message) => {
          setError(message);
          setState("error");
        },
      }),
    [context, token],
  );

  useEffect(() => {
    return () => stopAudio();
  }, []);

  async function submitVoice(text: string) {
    if (!authenticated || !token || busy) return;
    const contextual = buildContextualVoiceMessage(text, context);
    setState("processing");
    setError(null);
    try {
      const reply = await onSendToGod(contextual);
      setGodReply(reply);
      await speak(reply);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha na conversa por voz.");
      setState("error");
    }
  }

  async function speak(text: string) {
    if (!token) return;
    try {
      const audio = await api.synthesizeVoice(token, text);
      stopAudio();
      const url = URL.createObjectURL(audio);
      audioUrlRef.current = url;
      const player = new Audio(url);
      audioRef.current = player;
      player.onended = () => {
        stopAudio();
        setState("idle");
      };
      player.onerror = () => {
        stopAudio();
        setError("Falha ao reproduzir a voz de GOD.");
        setState("error");
      };
      setState("speaking");
      await player.play();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Voz indisponivel. Resposta mantida em texto.");
      setState("error");
    }
  }

  function stopAudio() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }

  function stopSpeaking() {
    stopAudio();
    setState("idle");
  }

  function handleTextSubmit(event: FormEvent) {
    event.preventDefault();
    const value = textInput.trim();
    if (!value) return;
    setTranscript(value);
    setTextInput("");
    void submitVoice(value);
  }

  if (!authenticated) return null;

  return (
    <section className="voice-conversation" data-state={state}>
      <div className="voice-topline">
        <VoiceButton
          state={state}
          supported={recognizer.supported}
          disabled={busy || state === "processing"}
          onListen={recognizer.start}
          onStopListening={recognizer.stop}
          onStopSpeaking={stopSpeaking}
        />
        <div>
          <strong>VOZ COM GOD</strong>
          <span>{state}</span>
        </div>
        {state === "error" ? (
          <button className="voice-clear" type="button" onClick={() => setState("idle")} aria-label="Limpar erro de voz">
            <X size={14} />
          </button>
        ) : null}
      </div>
      <dl className="voice-context">
        <div>
          <dt>CRIADOR</dt>
          <dd>{transcript || "Aguardando fala ou texto..."}</dd>
        </div>
        <div>
          <dt>GOD</dt>
          <dd>{godReply || lastGodReply || "Sem resposta nesta sessao."}</dd>
        </div>
      </dl>
      {error ? <p className="voice-error">{error}</p> : null}
      <form className="voice-text-fallback" onSubmit={handleTextSubmit}>
        <input value={textInput} onChange={(event) => setTextInput(event.target.value)} placeholder="Continuar por texto..." />
        <button disabled={busy || state === "processing" || !textInput.trim()} type="submit" aria-label="Enviar texto para GOD">
          <ArrowRight size={16} />
        </button>
      </form>
    </section>
  );
}
