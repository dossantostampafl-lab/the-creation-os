import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { converseWithDeus, createConversation, fetchConversationMessages } from "./api";
import type { ConversationMessage } from "./api";
import type { CosmosMood } from "./Cosmos";
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

  async function send(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const content = input.trim();
    if (!content || !enabled || pending) return;
    setPending(true);
    setError(null);
    onMoodChange?.("thinking");
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
      setMessages(await fetchConversationMessages(id));
      onMoodChange?.("speaking");
      window.setTimeout(() => onMoodChange?.("idle"), 4000);
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "CONVERSATION_FAILED";
      setError(message === "HTTP_503" ? "Inference provider is not configured." : "DEUS conversation failed.");
      onMoodChange?.("idle");
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
      <form className="console-form" onSubmit={send}>
        <textarea
          aria-label="Message DEUS"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={enabled ? "Speak to DEUS…" : "Configure an inference provider to speak to DEUS."}
          disabled={!enabled || pending}
          rows={1}
        />
        <button type="submit" aria-label="Send to DEUS" disabled={!enabled || pending || !input.trim()}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h14M13 6l6 6-6 6" /></svg>
        </button>
      </form>
      {error && <div className="console-error" role="alert">{error}</div>}
    </section>
  );
}
