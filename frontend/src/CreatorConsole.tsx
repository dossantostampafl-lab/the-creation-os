import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { converseWithDeus, createConversation, fetchConversationMessages } from "./api";
import type { ConversationMessage } from "./api";
import type { CosmosMood } from "./Cosmos";
import { useDeusEars, useDeusVoice, voiceText } from "./voice";
import "./CreatorConsole.css";

type Props = {
  enabled: boolean;
  onMoodChange?: (mood: CosmosMood) => void;
};

const CONVERSATION_KEY = "creation_conversation_id";

export function CreatorConsole({ enabled, onMoodChange }: Props) {
  const [conversationId, setConversationId] = useState(() => window.localStorage.getItem(CONVERSATION_KEY));
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const voice = useDeusVoice();
  const ears = useDeusEars({
    paused: pending || voice.speaking,
    onWake: () => voice.speak(voiceText.greeting()),
    onCommand: (text) => {
      setInput(text);
      void send(text);
    },
    onInterim: setInput,
  });

  useEffect(() => {
    if (pending) onMoodChange?.("thinking");
    else if (voice.speaking) onMoodChange?.("speaking");
    else if (ears.state === "attentive") onMoodChange?.("listening");
    else onMoodChange?.("idle");
  }, [pending, voice.speaking, ears.state, onMoodChange]);

  useEffect(() => {
    if (!conversationId) return;
    void fetchConversationMessages(conversationId)
      .then(setMessages)
      .catch(() => {
        window.localStorage.removeItem(CONVERSATION_KEY);
        setConversationId(null);
        setMessages([]);
      });
  }, [conversationId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending]);

  function voiceReply(latest: ConversationMessage[]) {
    const reply = [...latest].reverse().find((message) => message.role === "deus");
    if (reply) voice.speak(reply.content);
  }

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || !enabled || pending) return;
    voice.stop();
    setPending(true);
    setError(null);
    try {
      let id = conversationId;
      if (!id) {
        const conversation = await createConversation();
        id = conversation.id;
        window.localStorage.setItem(CONVERSATION_KEY, id);
        setConversationId(id);
      }
      setInput("");
      await converseWithDeus(id, content);
      const latest = await fetchConversationMessages(id);
      setMessages(latest);
      voiceReply(latest);
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "CONVERSATION_FAILED";
      setError(message === "HTTP_503" ? "Inference provider is not configured." : "DEUS conversation failed.");
    } finally {
      setPending(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <section className="creator-console" aria-labelledby="creator-console-title">
      <h2 id="creator-console-title" className="sr-only">Creator Console</h2>
      <div className="console-messages" ref={scrollRef} aria-live="polite">
        {messages.map((message) => (
          <div className={`console-message ${message.role === "deus" ? "deus-message" : "creator-message"}`} key={message.id}>
            <span>{message.role === "deus" ? "DEUS" : "CREATOR"}</span>
            <p>{message.content}</p>
          </div>
        ))}
        {pending && <div className="console-thinking" aria-label="DEUS is thinking"><i /><i /><i /></div>}
      </div>
      <form className="console-form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); void send(); }}>
        <textarea
          aria-label="Message DEUS"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={ears.state === "attentive" ? voiceText.listening() : enabled ? "Speak to DEUS…" : "Configure an inference provider to speak to DEUS."}
          disabled={!enabled || pending}
          rows={1}
        />
        {voice.supported && (
          <button
            type="button"
            className={`icon-button${voice.enabled ? " active" : ""}`}
            aria-label={voice.enabled ? "Mute DEUS voice" : "Unmute DEUS voice"}
            aria-pressed={voice.enabled}
            onClick={voice.toggle}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 9h4l5-4v14l-5-4H4z" />
              {voice.enabled ? <path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" /> : <path d="M16 9l5 6M21 9l-5 6" />}
            </svg>
          </button>
        )}
        {ears.supported && (
          <>
            <button
              type="button"
              className={`icon-button wake${ears.wakeEnabled ? " active" : ""}`}
              aria-label={ears.wakeEnabled ? "Turn off “Deus” wake word" : "Turn on “Deus” wake word"}
              aria-pressed={ears.wakeEnabled}
              disabled={!enabled}
              onClick={ears.toggleWake}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10a5 5 0 0 1 10 0c0 3-2 3.5-2.5 6a3 3 0 0 1-5.5 1.5M9.5 10a2.5 2.5 0 0 1 5 0" /></svg>
            </button>
            <button
              type="button"
              className={`icon-button mic${ears.state === "attentive" ? " live" : ""}`}
              aria-label={ears.state === "attentive" ? "Stop listening" : "Talk to DEUS"}
              aria-pressed={ears.state === "attentive"}
              disabled={!enabled || pending}
              onClick={ears.state === "attentive" ? ears.dismiss : () => { voice.stop(); ears.summon(); }}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></svg>
            </button>
          </>
        )}
        <button type="submit" aria-label="Send to DEUS" disabled={!enabled || pending || !input.trim()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h14M13 6l6 6-6 6" /></svg>
        </button>
      </form>
      {ears.state === "sleeping" && <div className="wake-hint" aria-live="polite"><i />{voiceText.wakeHint()}</div>}
      {(error ?? ears.error) && <div className="console-error" role="alert">{error ?? ears.error}</div>}
    </section>
  );
}
